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
| Secret | `/etc/my-expenses.env`, `root:docker` 0640, recovered from the snapshot |
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

Routine deploys no longer need this — Jenkins does them. Use it for break-glass
work, or to roll back: `IMAGE_TAG=b12 sudo docker compose -p my-expenses up -d`.

`/etc/my-expenses.env` is `root:docker` 0640, not 0600 as originally built. The
Jenkins deploy stage runs as uid 1000 and `docker compose` reads `env_file`
client-side, so a root-only secret made the stage fail. Members of the `docker`
group can therefore read it — which grants nothing new, since that group is
already root-equivalent through the socket. `sudo` stays the right habit for
manual work but is no longer strictly required for the `ubuntu` user.

The build stamp in the footer comes from the `APP_VERSION` build arg, which
`get_build_version()` checks first. `version.txt` is no longer used:

```bash
sudo APP_VERSION="v42 (abc1234)" docker compose up -d --build
```

## Backups

**Fixed 2026-10-27 ~06:22 UTC** with the API call below. Before applying it, a
manual snapshot of the data volume was taken: `snap-0c91e36820c1497e1`. That
is the first-ever backup of `vol-0e27d54dc4f62f922`. DLM does not manage it,
so retention will not delete it. The `infra/` module has been corrected to
match. Still to confirm: the first scheduled DLM snapshot, at the 2026-10-27
09:00 UTC window, using the verify command below.

The rest of this section is the original incident record.

**Broken 2026-10-18 to 2026-10-27 — the data volume had never been snapshotted.**

DLM policy `policy-0818ead367cbe2df7` is in state `ERROR` with
`StatusMessage: "Duplicate tag key 'Name' specified."` It last ran successfully
on 2026-10-17 and errored at the 09:00 UTC window on 2026-10-18.

Root cause: the schedule sets `CopyTags: true` *and* adds a `Name` tag of its
own (`expense-tracker-dlm-daily`). While the only volume in scope was the old
root volume, which carried no `Name` tag, the two never collided. The new data
volume is tagged `Name=expense-tracker-data`, so the copied `Name` and the
added `Name` now conflict and the whole policy fails — it does not skip the
volume, it stops.

This is the failure mode that outstanding item "no alerting on backup failure"
predicted: it broke silently, on the first day it mattered, and nothing said so.

Fix — drop `Name` from the schedule's `TagsToAdd` and let `CopyTags` supply it.
The policy is Terraform-managed (`aws_dlm_lifecycle_policy.daily_snapshots`),
but `infra/` is stale and must not be applied, so the live fix is a direct API
call and the module must be corrected to match:

```bash
aws dlm get-lifecycle-policy --region us-west-2 \
  --policy-id policy-0818ead367cbe2df7 --query 'Policy.PolicyDetails' > /tmp/dlm.json
# remove the {"Key":"Name",...} entry from Schedules[0].TagsToAdd, then:
aws dlm update-lifecycle-policy --region us-west-2 \
  --policy-id policy-0818ead367cbe2df7 --policy-details file:///tmp/dlm.json
```

Verify the next 09:00 UTC window actually produces a snapshot of
`vol-0e27d54dc4f62f922`:

```bash
aws ec2 describe-snapshots --region us-west-2 --owner-ids self \
  --filters "Name=volume-id,Values=vol-0e27d54dc4f62f922" \
  --query 'reverse(sort_by(Snapshots,&StartTime))[].{Id:SnapshotId,Start:StartTime,State:State}' --output table
```

Until that returns a row, **the only copy of `expenses.db` is the live volume.**

The eight snapshots of the old root volume (Oct 11–17 daily, plus the Oct 9
`expense-tracker-pre-dr-drill` baseline) are the historical record and include
the one the current DB was restored from (`snap-0c69dee2b99f8c280`). They are
orphaned from any live volume, so do not count on DLM retention leaving them
alone indefinitely — copy one aside if you want a permanent floor.

## Outstanding

1. **Confirm backups are running.** The DLM policy was fixed 2026-10-27 (see
   Backups). Until a scheduled DLM snapshot of `vol-0e27d54dc4f62f922` shows
   up, the manual `snap-0c91e36820c1497e1` is the only backup.
2. **`/opt/my-expenses` is not a git clone.** The tree was transferred directly
   because `templates/landing.html` and the Docker files were still uncommitted
   locally. They are pushed now, so this is unblocked — though the pipeline
   does not need it: Jenkins builds from its own workspace clone and deploys by
   image tag, and only `docker-compose.yml` is read from this directory.
   Converting it to a clone is drift protection, not a fix.
3. **Terraform is stale.** `infra/` still describes the terminated instance;
   its state was last written 2026-10-09. A `terraform apply` today would build
   a second AL2023/systemd instance and move the Elastic IP to it. Either
   `terraform import` this box or rewrite the module for the Docker setup
   before running Terraform again. The DLM tag fix above is a second reason the
   module needs editing.
4. **The root volume is unencrypted and unbacked-up.** That is now mostly fine —
   the DB and the app are elsewhere — except that `/etc/my-expenses.env` lives
   on it. Losing the root volume logs everyone out but destroys no data.
5. **Still no TLS and no alerting** on backup failure. Both predate this
   migration; the DLM breakage is the case for the alerting half.

## Resolved

- **CI/CD on Jenkins is live** (2026-10-18). `.github/workflows/deploy.yml` is
  deleted and the `EC2_*` GitHub secrets are unused by anything. Build **#2**
  was the first full run off a real push (`6f78dd8`): 54 tests passed inside
  the built image, the health gate saw `{"status":"ok","version":"b2 (6f78dd8)"}`,
  and `:latest` was promoted to b2. Build #1 failed with `Jenkinsfile not found`
  because it fired before the push — expected, and not a defect.
- **`/etc/my-expenses.env` group-readability**, needed by the deploy stage, is
  done (`root:docker` 0640). See "Operating it".
