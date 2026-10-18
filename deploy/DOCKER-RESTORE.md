# Docker restore — as built 2026-10-17

Record of moving the app off the terminated Terraform instance and onto the
hand-built Docker box, plus what is still outstanding.

## What happened

The original Terraform-managed instance (`i-02bd82719d36bb62c`, AL2023 +
systemd + nginx) was terminated 2026-10-17 22:50 UTC. Its root volume was
delete-on-termination, so `expenses.db` survived only in the DLM snapshots. The
replacement (`i-0e043dd454adfedd5`) is an Ubuntu 26.04 / arm64 `t4g.medium`
with Docker, created by hand outside Terraform.

The restore came from `snap-0c69dee2b99f8c280` (2026-10-17 09:24 UTC). Nothing
was lost: `expenses.db` had not been written since 2026-08-29, well before the
termination.

## Current layout

| Thing | Value |
|---|---|
| Instance | `i-0e043dd454adfedd5` (`t4g.medium`, arm64, us-west-2d) |
| Elastic IP | `32.184.38.172`, alloc `eipalloc-0fb16b2474219389d` — associated |
| App directory | `/opt/my-expenses` (not a git clone — see "Outstanding") |
| Data volume | `vol-0e27d54dc4f62f922`, 8 GB gp3, **encrypted**, `DeleteOnTermination=false` |
| Mounted at | `/mnt/expenses-data` via fstab UUID entry, `nofail` |
| DB | `/mnt/expenses-data/expenses.db` → `/data/expenses.db` in the container |
| Secret | `/etc/my-expenses.env`, root-owned 0600, recovered from the snapshot |
| Containers | `my-expenses-app-1` (gunicorn:5000), `my-expenses-nginx-1` (:80) |
| Shell access | SSM (`expense-tracker-ec2` instance profile) or the `oreo` SSH key |

Verified after restore: `pragma integrity_check` → `ok`, 7 users, 6 expenses,
`SECRET_KEY` 64 chars and not the dev fallback (so existing sessions survived),
`http://32.184.38.172/` → 200.

## Why the DB is on its own volume

This is the fix for exactly what went wrong. `expenses.db` used to live on a
delete-on-termination root volume, so terminating the instance destroyed it.
It is now on a separate encrypted volume that survives instance termination,
and the container only ever sees the `/data` bind mount — so the instance is
now disposable.

Two guards hold that together:

- The fstab entry is by **UUID**, not device name: nvme device ordering is not
  stable across attach order or reboots.
- `/etc/systemd/system/docker.service.d/10-wait-for-data-volume.conf` makes
  `docker.service` `Requires=` the mount unit. Without it Docker could start
  before the volume mounts and bind-mount an **empty** `/mnt/expenses-data`,
  whereupon `init_db()` would quietly create a fresh empty database while the
  real one sat unmounted. That fails loudly now instead.

## Operating it

```bash
cd /opt/my-expenses
sudo docker compose ps
sudo docker compose logs -f app
sudo docker compose up -d --build        # after a code change
```

`sudo` is required because `/etc/my-expenses.env` is root-owned 0600 — the same
protection the old systemd unit relied on via `EnvironmentFile`.

The build stamp in the footer comes from the `APP_VERSION` build arg, which
`get_build_version()` checks first. `version.txt` is no longer used:

```bash
sudo APP_VERSION="v42 (abc1234)" docker compose up -d --build
```

## Backups

The data volume is tagged `Project=expense-tracker`, which is what the DLM
policy targets, so daily snapshots cover it automatically. The first one lands
at the next 09:00 UTC window — **confirm it appears**:

```bash
aws ec2 describe-snapshots --region us-west-2 --owner-ids self \
  --filters "Name=volume-id,Values=vol-0e27d54dc4f62f922" \
  --query 'reverse(sort_by(Snapshots,&StartTime))[].{Id:SnapshotId,Start:StartTime,State:State}' --output table
```

The seven snapshots of the old root volume (Oct 11–17) plus the Oct 9
`expense-tracker-pre-dr-drill` baseline are the historical record. They are now
orphaned from any live volume, so do not count on DLM retention leaving them
alone indefinitely — copy one aside if you want a permanent floor.

## Outstanding

1. **`/opt/my-expenses` is not a git clone.** The tree was transferred directly
   because `templates/landing.html` and the Docker files were still uncommitted
   locally. Once they are pushed, replace it with a clone so `git pull` works.
2. **CI/CD moved to Jenkins on this box** (2026-10-18).
   `.github/workflows/deploy.yml` is deleted and the `EC2_*` GitHub secrets are
   no longer used by anything. See the CI/CD section of `CLAUDE.md`. The
   pipeline cannot run until the Docker files and `Jenkinsfile` are pushed to
   `main`, since Jenkins polls git for them.
3. **`/etc/my-expenses.env` must be group-readable by docker** for the deploy
   stage to work — `chown root:docker` + `chmod 640`. Jenkins runs as uid 1000
   and `docker compose` reads `env_file` client-side, so at 0600 root:root the
   deploy stage fails. The docker group is already root-equivalent through the
   socket, so this grants no capability that group did not already have.
4. **Terraform is stale.** `infra/` still describes the terminated instance;
   its state was last written 2026-10-09. A `terraform apply` today would build
   a second AL2023/systemd instance and move the Elastic IP to it. Either
   `terraform import` this box or rewrite the module for the Docker setup
   before running Terraform again.
5. **The root volume is unencrypted and unbacked-up.** That is now mostly fine —
   the DB and the app are elsewhere — except that `/etc/my-expenses.env` lives
   on it. Losing the root volume logs everyone out but destroys no data.
6. **Still no TLS and no alerting** on backup failure. Both predate this
   migration.
