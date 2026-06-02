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

cp "$APP_DIR/deploy/gunicorn.service" /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl enable gunicorn
systemctl start gunicorn

cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/conf.d/my-expenses.conf
systemctl enable nginx
systemctl start nginx
