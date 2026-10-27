# Describes the Docker box as it actually runs (rebuilt by hand 2026-10-17,
# adopted into Terraform by the import blocks in imports.tf). Two halves:
#
#   - Persistent: the data volume, its attachment, the Elastic IP and the DLM
#     policy. These carry `prevent_destroy` -- losing any of them loses data or
#     the public address, which is what went wrong with the previous instance.
#   - Disposable: the instance. Its root volume holds nothing that cannot be
#     rebuilt (see deploy/DOCKER-RESTORE.md), so replacing it costs minutes.
#
# Nothing here touches what runs *on* the box: the app, Jenkins and the
# /etc/*.env secrets are outside Terraform.

# ── Networking (default VPC) ───────────────────────────────────────────────

data "aws_vpc" "default" {
  default = true
}

# Pinned to one AZ, not "first default subnet": an EBS volume can only attach
# to an instance in its own AZ, and the data volume lives in us-west-2d.
data "aws_subnet" "app" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.availability_zone
  default_for_az    = true
}

# ── Security group ─────────────────────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "expense-tracker-app"
  description = "Expense tracker: HTTP from world, SSH from operator"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Shell access is SSM. SSH is opt-in for break-glass only, and only from one
  # address: leave ssh_cidr unset and port 22 stays closed.
  dynamic "ingress" {
    for_each = var.ssh_cidr == null ? [] : [var.ssh_cidr]
    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── IAM instance profile (SSM access for break-glass shell) ────────────────

resource "aws_iam_role" "ec2" {
  name = "expense-tracker-ec2"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "expense-tracker-ec2"
  role = aws_iam_role.ec2.name
}

# ── AMI lookup ─────────────────────────────────────────────────────────────

# Only used when the instance is (re)created -- `ignore_changes = [ami]` below
# keeps a newer Ubuntu image from replacing the running box.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-resolute-26.04-arm64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── EC2 instance (disposable) ──────────────────────────────────────────────

resource "aws_instance" "host" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnet.app.id
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  # IMDSv2 only. Hop limit 2 so containers (one network hop further away) can
  # still reach instance metadata.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # Unencrypted because that is how the box was built by hand, and flipping
  # this forces a replacement. Acceptable: nothing on the root volume is data
  # (the DB is on aws_ebs_volume.data). Encrypt on the next deliberate rebuild.
  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = false
  }

  tags = {
    Name = "expense-tracker"
  }

  lifecycle {
    # ami: Ubuntu ships new images often; each would otherwise replace the box.
    # user_data: the box was built by hand with none; first-boot provisioning
    #   for a replacement is not written yet (see README "Rebuilding").
    # ebs_block_device: the data volume is attached by aws_volume_attachment,
    #   and the provider would otherwise report it as drift here.
    ignore_changes = [ami, user_data, ebs_block_device]
  }
}

# ── Data volume (persistent) ───────────────────────────────────────────────

# Holds expenses.db. Separate from the instance so terminating the instance
# cannot take the data with it. The Project tag (from default_tags) is what
# puts it in scope for the DLM snapshots below.
resource "aws_ebs_volume" "data" {
  availability_zone = var.availability_zone
  size              = 8
  type              = "gp3"
  encrypted         = true

  tags = {
    Name = "expense-tracker-data"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdg"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.host.id

  # Destroying an attachment force-detaches the volume from a running box.
  # Replacing the instance should stop it first.
  stop_instance_before_detaching = true

  lifecycle {
    prevent_destroy = true
  }
}

# ── Automated EBS snapshots (DLM) ──────────────────────────────────────────
# Snapshots every volume tagged Project=expense-tracker -- in practice the data
# volume. Targeted by tag rather than volume id so the policy keeps working if
# the volume is ever replaced from a snapshot.
#
# Snapshots are crash-consistent, not quiesced -- SQLite recovers from that the
# same way it recovers from power loss, so no app coordination is needed.

resource "aws_iam_role" "dlm" {
  name        = "expense-tracker-dlm"
  description = "Lets Data Lifecycle Manager snapshot the expense-tracker volume"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "daily_snapshots" {
  description        = "expense-tracker daily volume snapshots"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Project = "expense-tracker"
    }

    schedule {
      name = "daily-${var.snapshot_retention_count}d"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = [var.snapshot_time_utc]
      }

      retain_rule {
        count = var.snapshot_retention_count
      }

      # Carry Project/ManagedBy onto the snapshots so they are attributable in
      # Cost Explorer and easy to find during a restore.
      copy_tags = true

      # No `Name` here: copy_tags already carries the volume's Name, and a
      # duplicate key fails the whole policy rather than skipping the volume.
      # That is how the data volume went unsnapshotted 2026-10-18 to 10-26.
      tags_to_add = {
        CreatedBy = "dlm"
      }
    }
  }

  depends_on = [aws_iam_role_policy_attachment.dlm]

  lifecycle {
    prevent_destroy = true
  }
}

# ── Elastic IP (persistent) ────────────────────────────────────────────────

resource "aws_eip" "app" {
  instance = aws_instance.host.id
  domain   = "vpc"

  tags = {
    Name = "expense-tracker"
  }

  lifecycle {
    prevent_destroy = true
  }
}
