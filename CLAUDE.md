# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Run in production
gunicorn app:app
```

Enable debug mode via environment variable (do not hardcode):
```bash
FLASK_DEBUG=true python app.py
```

```bash
# Run tests (requires venv)
python -m pytest tests/ -v
```

## Deployment (Docker, since 2026-10-17)

The app runs in Docker on an Ubuntu 26.04 / arm64 box (`i-0e043dd454adfedd5`) at the Elastic IP `32.184.38.172`. Two containers via `docker-compose.yml`: `app` (gunicorn on 5000, unpublished) and `nginx` (publishes 80, config in `deploy/nginx.docker.conf`). The app directory on the box is `/opt/my-expenses`.

`expenses.db` lives on a **separate encrypted EBS volume** (`vol-0e27d54dc4f62f922`) mounted at `/mnt/expenses-data` and bind-mounted to `/data` in the container. It is `DeleteOnTermination=false`, so terminating the instance no longer destroys the data — which is exactly what happened to the previous instance. `DB_PATH` in `app.py` is env-overridable for this reason; the local default is unchanged.

A systemd drop-in makes `docker.service` require the data-volume mount, so Docker cannot start before the volume is mounted and bind-mount an empty directory (which would make `init_db()` silently create a fresh, empty DB).

`SECRET_KEY` still comes from `/etc/my-expenses.env` (root-owned 0600), loaded by compose via `env_file` — so `docker compose` needs `sudo`. The footer build version comes from the `APP_VERSION` build arg, not `version.txt`.

Full as-built record, operating commands, and the outstanding items are in **`deploy/DOCKER-RESTORE.md`** — read it before touching the box.

## CI/CD (Jenkins, since 2026-10-18)

GitHub Actions is retired — `.github/workflows/deploy.yml` is deleted. Jenkins runs tests, builds, and deploys.

Jenkins lives in a container **on the app box itself**, as a separate compose project under `/opt/jenkins/` (Dockerfile, `docker-compose.yml`, `plugins.txt`, `jenkins.yaml`, `.env`). Deliberately separate from the app's compose project so restarting or breaking CI cannot disturb the running service.

- **It is published on `127.0.0.1:8080` only** and is not reachable from the Elastic IP. Reach the UI with an SSM port-forward:
  ```bash
  aws ssm start-session --target i-0e043dd454adfedd5 \
    --document-name AWS-StartPortForwardingSession \
    --parameters '{"portNumber":["8080"],"localPortNumber":["8080"]}'
  ```
  Then browse `http://localhost:8080` as `admin`; the password is in `/etc/jenkins.env` (root 0600).
- **The host docker socket is mounted**, which is root-equivalent on this host. That is the cost of letting Jenkins build images, and the reason nothing untrusted may run in this controller. `group_add` with the host docker GID (987) is what grants socket access; the GID is in `/opt/jenkins/.env`, which the compose CLI reads (`env_file` only reaches inside the container).
- **Configured by JCasC** (`/opt/jenkins/jenkins.yaml`), including the `my-expenses` pipeline job. `/var/jenkins_home` is on the unencrypted, unsnapshotted root volume, so anything configured only through the UI is lost with the box — make changes in `jenkins.yaml`, in git.
- **`/var/jenkins_home` is bind-mounted at the same path inside and outside the container.** This is required, not incidental: build contexts and bind-mount sources in the workspace are resolved by the *host* daemon, so the path must mean the same thing on both sides.
- **Triggered by SCM polling** (`H/2 * * * *`), not webhooks — a localhost-only Jenkins cannot receive them. Up to a 2-minute delay before a push is picked up.
- A 2 GB swapfile and `mem_limit: 2g` on the controller keep the JVM from getting gunicorn killed on a 3.8 GB box.

The pipeline is `Jenkinsfile` at the repo root: **Build** → **Test** → **Deploy** → **Health gate** → **Promote**.

- Tests run with `pytest` *inside the freshly built image*, so they exercise the real artifact rather than the source tree beside it. `requirements.txt` already carries pytest.
- Images are tagged `my-expenses-app:b<build>`. Only a build that passes the health gate is retagged `:latest`, so a bare `docker compose up -d` always lands on a known-good image. **Rollback:** `IMAGE_TAG=b12 docker compose -p my-expenses up -d`.
- The health gate polls `/healthz`, which reads SQLite. `/` and `/login` both render without touching the DB and would report healthy even with the data volume unmounted — the exact failure the gate exists to catch.
- `docker image prune -f` runs in `post { always }`; layers otherwise accumulate on the 30 GB root volume.

## Infrastructure (Terraform)

**Stale as of 2026-10-17:** the state in S3 was last written 2026-10-09 and still describes the terminated instance `i-02bd82719d36bb62c`. The current box was created by hand, outside Terraform. A `terraform apply` today would build a *second* AL2023/systemd instance and move the Elastic IP to it. Import or rewrite the module before running Terraform again.

Terraform (`infra/`) owns the AWS infrastructure the app runs on — it never touches app code or `expenses.db`. Full runbook (credentials, apply order, day-2 ops) is in `infra/README.md`.

- **`infra/bootstrap/`** — one-time module with *local* state that creates the remote state backend: a versioned, encrypted, public-access-blocked S3 bucket and a DynamoDB lock table. Must be applied before the main module, which keeps its state there (`backend.tf`).
- **`infra/`** (main module) — the EC2 instance (`t3.micro`, latest AL2023 AMI, 30 GB encrypted gp3), an Elastic IP, a security group (port 80 open to the world, port 22 limited to the required `ssh_cidr` var), and an IAM role with `AmazonSSMManagedInstanceCore` for break-glass SSM access. It also *generates* the SSH keypair and writes the private key to `infra/.ssh/expense-tracker.pem`.
- `terraform output public_ip` and the generated `.pem` are where the `EC2_HOST` and `EC2_SSH_KEY` GitHub secrets come from. Any apply that replaces the instance or EIP means re-pasting them.
- **`aws_instance.app` carries `lifecycle { ignore_changes = [ami] }`.** AL2023 ships new AMIs frequently; without it, every plan after an AMI release would replace the instance and wipe the SQLite DB. Replace only deliberately — `terraform taint aws_instance.app` — and know it destroys the data.
- **`aws_dlm_lifecycle_policy.daily_snapshots`** takes daily EBS snapshots of every volume tagged `Project=expense-tracker`, retaining `snapshot_retention_count` (7) of them. It targets the *tag*, not a volume id, so it keeps working across instance replacement — but a volume created outside Terraform is only covered if someone tags it. The current data volume is tagged.
- `infra/user_data.sh.tpl` is cloud-init first-boot provisioning that duplicates `deploy/setup.sh`. Change one without the other and newly created instances diverge from the existing one.
- Not managed by Terraform: app code (deployed by GitHub Actions), `expenses.db` (lives on the EBS volume), TLS/HTTPS, and DNS.

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates and a SQLite database.

- **`app.py`** — all routes, DB init, and form validation. `get_db()` opens a new SQLite connection per request using `sqlite3.Row` for dict-like row access. `init_db()` is called once at startup. All form input goes through `validate_expense_form()` before any DB write.
- **`/` is public.** Logged-out visitors get `templates/landing.html` — a read-only marketing preview built from the `SAMPLE_EXPENSES` constant in `app.py`, dated into the current month by `sample_expenses()`. Logged-in users get their own dashboard (`index.html`). `/add`, `/edit`, and `/delete` remain `@login_required`.
- **Sample data is baked in, not fetched.** The figures are real: BLS Consumer Expenditure Survey 2024 for everyday categories, Census ACS 2024 1-year medians for rent and mortgage. `scripts/refresh_sample_costs.py` re-pulls the BLS half (no API key needed) and prints a paste-ready block; the two Census figures need a free key and are transcribed by hand. The reasoning behind each number — why the CE rent series is unusable, why utilities are subtracted from the Census figures — is documented in the comment above `SAMPLE_EXPENSES`. Read it before changing any amount.
- **`expenses.db`** — auto-generated on first run, not committed to git.
- **`templates/`** — `base.html` holds the full layout, CSS (CSS variables), and Bootstrap 5 CDN links. All other templates extend it via `{% block content %}`.

## Key conventions

- `CATEGORIES` in `app.py` is the single source of truth for allowed categories (`Housing`, `Food`, `Transport`, `Entertainment`, `Utilities`, `Other`). Templates and validation both reference it — keep them in sync.
- All form validation (required fields, positive amount, valid category, date format `YYYY-MM-DD`) is handled in `validate_expense_form()`. Add new validation there, not inline in route handlers.
- Category badge styling is driven by CSS classes named `cat-<CategoryName>` in `base.html`. Adding a new category requires a matching CSS rule.
- Delete uses `POST`, not `GET`, to prevent accidental deletion via link prefetch.
