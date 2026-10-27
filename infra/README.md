# Infrastructure

Terraform owns the AWS resources the app runs on: the EC2 instance, its data
volume, the Elastic IP, the security group, the IAM roles and the DLM snapshot
policy. It does not touch what runs *on* the box: the app and Jenkins
containers, `/etc/*.env` secrets, or `expenses.db` itself. Those are covered in
`deploy/DOCKER-RESTORE.md` and the root `CLAUDE.md`.

## What it manages

| Resource | Address | On destroy |
|---|---|---|
| Data volume (`expenses.db`) | `aws_ebs_volume.data` | **`prevent_destroy`** |
| Its attachment at `/dev/sdg` | `aws_volume_attachment.data` | **`prevent_destroy`** |
| Elastic IP `32.184.38.172` | `aws_eip.app` | **`prevent_destroy`** |
| Daily snapshots of the data volume | `aws_dlm_lifecycle_policy.daily_snapshots` | **`prevent_destroy`** |
| Instance (Ubuntu 26.04 arm64, `t4g.medium`) | `aws_instance.host` | disposable |
| Security group (80 open; 22 only if `ssh_cidr` is set) | `aws_security_group.app` | |
| SSM instance role, DLM role | `aws_iam_role.ec2`, `aws_iam_role.dlm` | |

The split is the lesson of 2026-10-17, when terminating the old instance also
destroyed its root volume and the database with it. The data now lives on its
own volume, and Terraform refuses any plan that would destroy it.

The instance is disposable in principle, but **there is no automated rebuild
yet** — see "Rebuilding" below.

## Prerequisites

- Terraform >= 1.7 (the module uses `removed` blocks)
- AWS CLI with the `luna` profile, region `us-west-2`
- The state backend from `bootstrap/` (already exists; see below)

```
export AWS_PROFILE=luna          # bash
$env:AWS_PROFILE = "luna"        # PowerShell
```

## Day-to-day

```
cd infra
terraform init
terraform plan
```

**Read every plan before applying.** Anything that replaces `aws_instance.host`
(`-/+` or "must be replaced") rebuilds the server by hand afterwards. Anything
that touches the four `prevent_destroy` resources errors out by design — if you
ever see that error, stop and work out why rather than removing the guard.

Arguments that force an instance replacement if changed: `availability_zone`,
`key_name`, the subnet, and the root volume's `encrypted` flag. Changing
`instance_type` is in-place (AWS stops and starts the box).

### Opening SSH temporarily

Port 22 is closed unless `ssh_cidr` is set; SSM (`terraform output
ssm_shell_command`) is the normal way in. The operator's home IP lives in
`infra/terraform.tfvars`, which Terraform loads automatically and which is
**gitignored because the repo is public**:

```
ssh_cidr = "1.2.3.4/32"
```

When your IP changes, update that file and apply. Without the file (e.g. a
fresh clone), a plan will propose closing port 22. That's safe, but it's not
what you want if you rely on SSH.

## Rebuilding

Not automated. `user_data` is in `ignore_changes`, and the box has none — it was
built by hand. A replacement instance would come up as a bare Ubuntu box with
the data volume attached but not mounted. Until a Docker-era cloud-init script
exists, rebuilding means repeating the steps in `deploy/DOCKER-RESTORE.md`
(install Docker, fstab UUID mount, the `docker.service` drop-in, compose up,
Jenkins). Writing that script is the next piece of work here.

## Adoption history

The current box was created outside Terraform on 2026-10-17 and adopted with the
`import` and `removed` blocks in `imports.tf`, applied 2026-10-27. That file is
now a no-op, kept as the record of why the instance address is `.host`.

The previous AL2023 design (generated SSH key, `user_data` cloud-init, GitHub
Actions deploys) is retired; see git history before October 2026.

## State backend (`bootstrap/`)

One-time module with *local* state that created the remote backend: a
versioned, encrypted, public-access-blocked S3 bucket
(`expense-tracker-tf-state-870757819272`) and a DynamoDB lock table. It is
already applied; do not re-run it. S3 versioning means every past state is
recoverable if an apply goes wrong.
