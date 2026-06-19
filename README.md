# football.groupcaliber.ai — setup guide

## What you need before starting
- Claude Code open on your PC in this project folder
- SSH access to the same server running vlad.groupcaliber.ai
- The server IP address

---

## Step 1 — Get the files onto your PC

Tell Claude Code:
> "I've downloaded the football-caliber project folder. Install the Python dependencies."

Claude Code will run:
```
pip install -r requirements.txt
```

---

## Step 2 — Test it locally first

Tell Claude Code:
> "Start the server locally on port 8001."

Claude Code will run:
```
uvicorn server:app --reload --port 8001
```

Open http://localhost:8001 in your browser. You should see the sweepstake table
and the badge should say "● Live · 28 results" after a few seconds.

---

## Step 3 — Copy files to the server

Tell Claude Code:
> "Copy the football-caliber folder to the server at [SERVER_IP]."

Or do it manually via WinSCP / scp:
```
scp -r football-caliber/ user@YOUR_SERVER_IP:/var/www/football-caliber/
```

---

## Step 4 — Install dependencies on the server

SSH into the server, then:
```bash
cd /var/www/football-caliber
pip install -r requirements.txt
```

---

## Step 5 — Start the server as a background service

Tell Claude Code (or do manually on the server):
```bash
uvicorn server:app --host 0.0.0.0 --port 8001 &
```

To make it survive reboots, ask Claude Code:
> "Set up a systemd service for the football app on the server."

---

## Step 6 — Add the Nginx config

On the server, add to your Nginx config (same file as vlad.groupcaliber.ai):

```nginx
server {
    listen 80;
    server_name football.groupcaliber.ai;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name football.groupcaliber.ai;
    # Uses the same wildcard *.groupcaliber.ai SSL cert — no new cert needed
    ssl_certificate     /path/to/your/wildcard.crt;
    ssl_certificate_key /path/to/your/wildcard.key;
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then reload Nginx:
```bash
nginx -t && systemctl reload nginx
```

---

## Step 7 — Add the DNS record

In your DNS provider (wherever groupcaliber.ai is managed):
- Type: `A`
- Name: `football`
- Value: same IP as `vlad.groupcaliber.ai`
- TTL: 300

---

## Step 8 — Verify

Open https://football.groupcaliber.ai — you should see the table live.

---

## Keeping the data current

The scores update automatically from the openfootball GitHub feed whenever someone
clicks Refresh. No action needed from you for match results.

**For cards (yellow/red):** after each matchday, tell Claude Code:
> "Update the card data in index.html with yesterday's bookings: [paste the card counts]"

Claude Code will update the CARD_DATA object in static/index.html and restart the server.
