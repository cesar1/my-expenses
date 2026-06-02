# Infrastructure

Terraform manages the EC2 instance, Elastic IP, security group, IAM role, and
SSH key for the expense tracker. The app itself is still deployed by GitHub
Actions over SSH (see `.github/workflows/deploy.yml`) — Terraform only owns
the AWS infra.

## Prerequisites

- Terraform >= 1.5
- AWS CLI configured (see below)
- An IAM user with permission to create EC2/S3/DynamoDB/IAM resources

## AWS credentials

1. In the AWS console, create an IAM user with `AdministratorAccess`.
2. Generate an access key for it (Security credentials → Create access key).
3. Configure the AWS CLI locally:
   ```
   aws configure --profile Caps
   ```
   Paste the access key and secret, set region to `us-west-2`.
4. Tell Terraform which profile to use:
   - PowerShell: `$env:AWS_PROFILE = "Caps"`
   - bash: `export AWS_PROFILE=Caps`

## One-time bootstrap

The S3 state bucket and DynamoDB lock table have to exist before the main
module can use them. The bootstrap module creates them with local state.

```
cd infra/bootstrap
terraform init
terraform apply -var "state_bucket_name=<your-globally-unique-bucket-name>"
```

A safe pattern for the bucket name: `expense-tracker-tf-state-<your-aws-account-id>`.

Commit the resulting `terraform.tfstate` if you want a backup, or leave it
gitignored — it only contains the bucket + table, both easy to recreate.

## Point the main module at the new state bucket

Edit `infra/backend.tf` and replace the `bucket` value with the name you used
in the bootstrap step.

## Apply

```
cd infra
terraform init
terraform apply -var "ssh_cidr=$(curl -s https://checkip.amazonaws.com)/32"
```

(Or pass `-var "ssh_cidr=1.2.3.4/32"` explicitly.)

Apply takes ~3 minutes. Cloud-init runs after the instance is up and takes
another ~2 minutes — the app won't respond on port 80 until that finishes.
To watch progress:

```
ssh -i ./.ssh/expense-tracker.pem ec2-user@<public-ip>
sudo tail -f /var/log/cloud-init-output.log
```

## Wire up GitHub Actions

After the apply succeeds, grab the values you need:

```
terraform output public_ip
type .\.ssh\expense-tracker.pem       # PowerShell
cat ./.ssh/expense-tracker.pem        # bash
```

In your repo on GitHub → Settings → Secrets and variables → Actions, update:

| Secret         | Value                                             |
|----------------|---------------------------------------------------|
| `EC2_HOST`     | the public IP from `terraform output public_ip`   |
| `EC2_USER`     | `ec2-user`                                        |
| `EC2_SSH_KEY`  | full pem contents (include BEGIN/END lines)       |

The next push to `main` will deploy.

## Day-2 ops

- **Tighten SSH CIDR when your IP changes:** `terraform apply -var "ssh_cidr=<new-ip>/32"`
- **Replace the instance deliberately:** `terraform taint aws_instance.app && terraform apply` — this wipes the SQLite DB.
- **Tear down everything:** `terraform destroy` removes the EC2, EIP, SG, IAM. The state bucket and lock table survive (they live in `bootstrap/`).
- **Update the AMI:** the `ignore_changes = [ami]` block in `main.tf` keeps Terraform from replacing the instance every time Amazon ships a new AL2023 image. Remove or override that block when you want a refresh.

## What this manages — and what it doesn't

| Owned by Terraform                | Not owned                         |
|-----------------------------------|-----------------------------------|
| EC2, EIP, SG, IAM role, SSH keys  | App code (deployed by Actions)    |
| Default VPC reference             | The SQLite DB (lives on the EBS)  |
| State bucket + lock table         | TLS, HTTPS, DNS                   |
