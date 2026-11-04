# Deploying the dashboard to EC2

The dashboard runs as a systemd service on `127.0.0.1:8501`. nginx sits in front of it on port **8888**. There is no domain, so you open it at `http://<public-ip>:8888/`. The dashboard shows its own password screen.

## Install

```bash
ssh -i key.pem ubuntu@<public-ip>
sudo apt-get update && sudo apt-get install -y git
git clone -b deploy https://github.com/AswinBalajiTR/Grad-Research.git
cd Grad-Research
bash deploy/setup.sh    # prompts for the dashboard password
```
Open `http://<public-ip>:8888/` and enter the password.

## Restricted access

Two things restrict access: the security group only lets GWU IP ranges in, and the dashboard asks for a password. Everyone uses the same password. 

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
