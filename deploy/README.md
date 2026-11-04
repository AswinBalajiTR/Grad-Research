# Deploying the dashboard to EC2

The dashboard runs as a systemd service on `127.0.0.1:8501`. nginx sits in front of it on port 80 and asks for a password. There is no domain, so you open it at the instance's public IP.

H-1B data is not refreshed on the server. The page shows `data/h1b/processed/h1b_filings_2025_to_latest.csv`, which is not in git; copy it up yourself (step 3). To update it, run `python code/h1b/collect_h1b.py --source dol --auto` locally, then copy the new CSV again and restart the service.

## 1. Launch the instance

- AMI: Ubuntu 24.04 LTS. Type: **t3.small** (2 GB RAM). Disk: 20 GB gp3.
- Allocate an **Elastic IP** and associate it, so the address doesn't change on restart.
- Security group inbound rules:
  - SSH 22 from **My IP**
  - HTTP 80 from **My IP**, plus the IPs of anyone else who needs access (e.g. GWU network ranges)

  Don't open port 8501.

## 2. Install

```bash
ssh -i key.pem ubuntu@<elastic-ip>
sudo apt-get update && sudo apt-get install -y git
git clone -b deploy https://github.com/AswinBalajiTR/Grad-Research.git
cd Grad-Research
bash deploy/setup.sh <login-username>    # prompts for the dashboard password
```

## 3. Copy the H-1B data

From your own machine, in the repo root:

```bash
ssh -i key.pem ubuntu@<elastic-ip> mkdir -p Grad-Research/data/h1b/processed
scp -i key.pem data/h1b/processed/h1b_filings_2025_to_latest.csv ubuntu@<elastic-ip>:~/Grad-Research/data/h1b/processed/
ssh -i key.pem ubuntu@<elastic-ip> sudo systemctl restart dashboard
```

Open `http://<elastic-ip>/` and log in.

## Restricted access

Access is limited in two ways: the security group only allows listed IPs, and nginx asks for a password. Without a domain there's no HTTPS, so the password is sent unencrypted. That's why the IP allowlist is the main protection; keep it narrow.

Add another login: `sudo htpasswd /etc/nginx/.htpasswd <name>` (no `-c`, which would overwrite the file).

## Updating

```bash
cd ~/Grad-Research
git pull
.venv/bin/pip install -r requirements.txt   # only if requirements changed
sudo systemctl restart dashboard
```

## Troubleshooting

- App logs: `journalctl -u dashboard -f`
- nginx errors: `sudo tail -f /var/log/nginx/error.log`
- Page stuck on "Connecting": the websocket headers in `nginx-dashboard.conf` are missing.
- 502 Bad Gateway: the service isn't running; check `systemctl status dashboard`.
