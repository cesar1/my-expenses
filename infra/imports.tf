# One-time adoption of the hand-built Docker box (2026-10-17) into this state.
# Import blocks are idempotent: once an apply has recorded these resources,
# they are no-ops and can be deleted along with this file.
#
# The security group, IAM roles, instance profile, EIP and DLM policy needed
# no import -- the rebuild reused them and they were already in state.

import {
  to = aws_instance.host
  id = "i-0e043dd454adfedd5"
}

# aws_instance.app is the instance terminated 2026-10-17 (i-02bd82719d36bb62c).
# The live box is imported as aws_instance.host instead because Terraform will
# not import into an address that state already holds. There is nothing left
# in AWS to destroy; this only drops the stale record.
removed {
  from = aws_instance.app
  lifecycle {
    destroy = false
  }
}

import {
  to = aws_ebs_volume.data
  id = "vol-0e27d54dc4f62f922"
}

import {
  to = aws_volume_attachment.data
  id = "/dev/sdg:vol-0e27d54dc4f62f922:i-0e043dd454adfedd5"
}

# The generated "expense-tracker" key pair belonged to the terminated instance;
# the current box uses the hand-made "oreo" key (var.key_name). Forget these
# rather than destroy them: `destroy = false` leaves the AWS key pair and the
# local .pem alone, and drops the private key out of the remote state.
removed {
  from = aws_key_pair.ec2
  lifecycle {
    destroy = false
  }
}

removed {
  from = tls_private_key.ec2
  lifecycle {
    destroy = false
  }
}

removed {
  from = local_sensitive_file.private_key
  lifecycle {
    destroy = false
  }
}
