#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu EC2 instance, run from the repo root:
#   bash deploy/setup.sh <login-username>
set -euo pipefail

USERNAME="${1:?usage: bash deploy/setup.sh <login-username>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

sudo apt-get update
sudo apt-get install -y python3-venv python3-pip nginx apache2-utils

python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install --upgrade pip
"$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"

# Prompts for the dashboard password.
sudo htpasswd -c /etc/nginx/.htpasswd "$USERNAME"

sudo cp "$REPO/deploy/dashboard.service" /etc/systemd/system/dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard

sudo cp "$REPO/deploy/nginx-dashboard.conf" /etc/nginx/sites-available/dashboard
sudo ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/dashboard
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "Done. Open http://<instance-public-ip>/ and log in as $USERNAME."
