# Deploying the dashboard to EC2

The dashboard runs as a systemd service on `127.0.0.1:8501`. nginx sits in front of it on port **8888**, the port the security group already allows from GWU networks. There is no domain, so you open it at `http://<public-ip>:8888/`. The dashboard shows its own password screen.

H-1B data is not refreshed on the server. The page shows `data/h1b/processed/h1b_filings_2025_to_latest.csv`, which is not in git; copy it up yourself (step 3). To update it, run `python code/h1b/collect_h1b.py --source dol --auto` locally, then copy the new CSV again and restart the service.

## 1. Instance

- Ubuntu 24.04 LTS, **t3.small** (2 GB RAM) or larger, 20 GB disk.
- Security group: inbound TCP **8888** (and SSH 22) from `128.164.0.0/16` and `161.253.0.0/16`. Only GWU networks can reach the dashboard. Don't open port 8501.
- Nothing else (e.g. Jupyter) can be using port 8888: `sudo ss -ltnp | grep 8888` should print nothing.

## 2. Install

```bash
ssh -i key.pem ubuntu@<public-ip>
sudo apt-get update && sudo apt-get install -y git
git clone -b deploy https://github.com/AswinBalajiTR/Grad-Research.git
cd Grad-Research
bash deploy/setup.sh    # prompts for the dashboard password
```

## 3. Copy the H-1B data

From your own machine, in the repo root:

```bash
ssh -i key.pem ubuntu@<public-ip> mkdir -p Grad-Research/data/h1b/processed
scp -i key.pem data/h1b/processed/h1b_filings_2025_to_latest.csv ubuntu@<public-ip>:~/Grad-Research/data/h1b/processed/
ssh -i key.pem ubuntu@<public-ip> sudo systemctl restart dashboard
```

Open `http://<public-ip>:8888/` and enter the password.

## Restricted access

Two things restrict access: the security group only lets GWU IP ranges in, and the dashboard asks for a password. Everyone uses the same password. It's stored in `.streamlit/secrets.toml` on the server, which is not in git.

The dashboard shows its own password screen rather than using a browser login box: GWU-managed Chrome/Edge (`AuthSchemes = ntlm,negotiate`) never shows browser login boxes. There's no HTTPS without a domain, so the password is sent unencrypted; the IP restriction is the main protection.

Change the password:

```bash
nano ~/Grad-Research/.streamlit/secrets.toml    # password = "new-password"
sudo systemctl restart dashboard
```

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
- Browser times out: you're off the GWU network, or something else holds port 8888.
- Page stuck on "Connecting": the websocket headers in `nginx-dashboard.conf` are missing.
- 502 Bad Gateway: the service isn't running; check `systemctl status dashboard`.
