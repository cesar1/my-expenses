#!/bin/bash
# One-time EC2 setup script. Run this after launching your instance.
# For Amazon Linux 2. If using Ubuntu, replace yum with apt-get.

set -e

REPO_URL="https://github.com/YOUR_USERNAME/my-expenses.git"
APP_DIR="$HOME/my-expenses"

# System packages
sudo yum update -y
sudo yum install -y python3 python3-pip nginx git

# Clone repo
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Application secrets — generate SECRET_KEY once. Persists across deploys and is
# never committed to git. Re-running setup.sh keeps the existing key (so users
# stay logged in).
SECRET_ENV_FILE="/etc/my-expenses.env"
if [ ! -f "$SECRET_ENV_FILE" ]; then
  echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" \
    | sudo tee "$SECRET_ENV_FILE" > /dev/null
  sudo chmod 600 "$SECRET_ENV_FILE"
fi

# Initialize the database
python -c "import app; app.init_db()"

# Gunicorn systemd service
sudo cp deploy/gunicorn.service /etc/systemd/system/gunicorn.service
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn

# Nginx
sudo cp deploy/nginx.conf /etc/nginx/conf.d/my-expenses.conf
sudo systemctl enable nginx
sudo systemctl start nginx

echo "Setup complete. App running at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
