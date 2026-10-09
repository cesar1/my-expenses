#!/bin/bash
# Runs once on first boot as root via cloud-init.
# Mirrors deploy/setup.sh but parameterized for Terraform.

set -euxo pipefail

dnf update -y
dnf install -y python3 python3-pip nginx git

REPO_URL="${github_repo_url}"
APP_DIR="/home/ec2-user/my-expenses"

sudo -u ec2-user git clone "$REPO_URL" "$APP_DIR"
sudo -u ec2-user python3 -m venv "$APP_DIR/venv"
sudo -u ec2-user "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
sudo -u ec2-user bash -c "cd $APP_DIR && $APP_DIR/venv/bin/python -c 'import app; app.init_db()'"

# Generate SECRET_KEY once, before gunicorn first starts. Without this file the
# app falls back to the insecure dev key hardcoded in app.py -- which is public
# -- and anyone could forge a session cookie. gunicorn.service uses
# "EnvironmentFile=-", so a missing file fails open silently rather than loudly.
# Mirrors deploy/setup.sh and the ensure-secret step in deploy.yml.
SECRET_ENV_FILE="/etc/my-expenses.env"
if [ ! -f "$SECRET_ENV_FILE" ]; then
  # xtrace off: keep the key out of /var/log/cloud-init-output.log, which is
  # world-readable. Re-enabled immediately after.
  set +x
  NEW_SECRET="$("$APP_DIR/venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"
  printf 'SECRET_KEY=%s\n' "$NEW_SECRET" > "$SECRET_ENV_FILE"
  unset NEW_SECRET
  set -x
  chown root:root "$SECRET_ENV_FILE"
  chmod 600 "$SECRET_ENV_FILE"
fi

cp "$APP_DIR/deploy/gunicorn.service" /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl enable gunicorn
systemctl start gunicorn

cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/conf.d/my-expenses.conf
systemctl enable nginx
systemctl start nginx
