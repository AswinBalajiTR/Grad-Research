#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu EC2 instance, run from the repo root:
#   bash deploy/setup.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"

sudo apt-get update
sudo apt-get install -y python3-venv python3-pip nginx

python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install --upgrade pip
"$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"

# The dashboard asks for this password on its own login screen.
read -rsp "Dashboard password: " PASSWORD
echo
mkdir -p "$REPO/.streamlit"
PASSWORD="$PASSWORD" python3 -c 'import json, os; print("password = " + json.dumps(os.environ["PASSWORD"]))' \
    > "$REPO/.streamlit/secrets.toml"
chmod 600 "$REPO/.streamlit/secrets.toml"

sudo cp "$REPO/deploy/dashboard.service" /etc/systemd/system/dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard

sudo cp "$REPO/deploy/nginx-dashboard.conf" /etc/nginx/sites-available/dashboard
sudo ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/dashboard
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "Done. Open http://<instance-public-ip>:8888/ and enter the password."
