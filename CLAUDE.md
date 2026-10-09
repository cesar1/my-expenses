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

## CI/CD

Deployments are automated via GitHub Actions (`.github/workflows/deploy.yml`). Every push to `main` SSHs into the EC2 instance, runs `git pull`, reinstalls dependencies into the venv, and restarts the gunicorn systemd service.

**Required GitHub repo secrets:** `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`

The Flask `SECRET_KEY` (for login sessions) is **not** a GitHub secret. It is generated once on the EC2 box and stored in `/etc/my-expenses.env` (chmod 600, root-owned), loaded by the gunicorn systemd unit via `EnvironmentFile`. Both `deploy/setup.sh` and the deploy workflow create it only if missing, so it persists across deploys and users stay logged in. Locally, `app.py` falls back to an insecure dev key.

The site footer shows a build version, resolved once at startup by `get_build_version()` in `app.py`: `APP_VERSION` env var, then `version.txt`, then the local git SHA (shown as `dev-<sha>`), then `dev`. `version.txt` is untracked and written on the box — by the deploy workflow after `git pull` (`v<run_number> (<short_sha>)`) and by `deploy/setup.sh` on first bootstrap. Git is the last resort because `gunicorn.service` pins `PATH` to the venv, so `git` is not on `PATH` in production.

On EC2 the app runs under systemd (`gunicorn.service`) behind nginx (`nginx.conf` proxies port 80 → 127.0.0.1:5000). One-time EC2 bootstrap is in `deploy/setup.sh`. The SQLite database (`expenses.db`) lives on the EBS volume and is never touched by deployments.

## Infrastructure (Terraform)

Terraform (`infra/`) owns the AWS infrastructure the app runs on — it never touches app code or `expenses.db`. Full runbook (credentials, apply order, day-2 ops) is in `infra/README.md`.

- **`infra/bootstrap/`** — one-time module with *local* state that creates the remote state backend: a versioned, encrypted, public-access-blocked S3 bucket and a DynamoDB lock table. Must be applied before the main module, which keeps its state there (`backend.tf`).
- **`infra/`** (main module) — the EC2 instance (`t3.micro`, latest AL2023 AMI, 30 GB encrypted gp3), an Elastic IP, a security group (port 80 open to the world, port 22 limited to the required `ssh_cidr` var), and an IAM role with `AmazonSSMManagedInstanceCore` for break-glass SSM access. It also *generates* the SSH keypair and writes the private key to `infra/.ssh/expense-tracker.pem`.
- `terraform output public_ip` and the generated `.pem` are where the `EC2_HOST` and `EC2_SSH_KEY` GitHub secrets come from. Any apply that replaces the instance or EIP means re-pasting them.
- **`aws_instance.app` carries `lifecycle { ignore_changes = [ami] }`.** AL2023 ships new AMIs frequently; without it, every plan after an AMI release would replace the instance and wipe the SQLite DB. Replace only deliberately — `terraform taint aws_instance.app` — and know it destroys the data.
- `infra/user_data.sh.tpl` is cloud-init first-boot provisioning that duplicates `deploy/setup.sh`. Change one without the other and newly created instances diverge from the existing one.
- Not managed by Terraform: app code (deployed by GitHub Actions), `expenses.db` (lives on the EBS volume), TLS/HTTPS, and DNS.

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates and a SQLite database.

- **`app.py`** — all routes, DB init, and form validation. `get_db()` opens a new SQLite connection per request using `sqlite3.Row` for dict-like row access. `init_db()` is called once at startup. All form input goes through `validate_expense_form()` before any DB write.
- **`expenses.db`** — auto-generated on first run, not committed to git.
- **`templates/`** — `base.html` holds the full layout, CSS (CSS variables), and Bootstrap 5 CDN links. All other templates extend it via `{% block content %}`.

## Key conventions

- `CATEGORIES` in `app.py` is the single source of truth for allowed categories. Templates and validation both reference it — keep them in sync.
- All form validation (required fields, positive amount, valid category, date format `YYYY-MM-DD`) is handled in `validate_expense_form()`. Add new validation there, not inline in route handlers.
- Category badge styling is driven by CSS classes named `cat-<CategoryName>` in `base.html`. Adding a new category requires a matching CSS rule.
- Delete uses `POST`, not `GET`, to prevent accidental deletion via link prefetch.
