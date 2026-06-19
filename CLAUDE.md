# football-caliber — Claude Code project brief

## What this is
A lightweight internal web app for the Caliber office World Cup 2026 sweepstake.
Deployed at football.groupcaliber.ai.

## Stack
- **Backend:** Python, FastAPI, uvicorn
- **Frontend:** Single HTML file (static/index.html) — vanilla JS, no build step
- **Data source:** openfootball/worldcup.json on GitHub (fetched server-side via /api/matches)
- **Flags:** flag-icons CSS library via CDN (cdn.jsdelivr.net)

## Project structure
```
football-caliber/
  server.py          ← FastAPI app + /api/matches proxy endpoint
  requirements.txt
  static/
    index.html       ← entire frontend (HTML + CSS + JS in one file)
  CLAUDE.md          ← this file
```

## How to run locally
```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8001
```
Then open http://localhost:8001

## How to run in production
```bash
uvicorn server:app --host 0.0.0.0 --port 8001
```
Nginx proxies football.groupcaliber.ai → localhost:8001 (same pattern as vlad.groupcaliber.ai).

## Key logic (do not break these)

### Player–team mapping
Each of the 16 players has exactly 3 teams. The mapping lives in `static/index.html`
in the `PT` object. Do not change it without confirming with Vlad.

### Score parsing
The openfootball feed uses `match.score.ft[0]` and `match.score.ft[1]` — NOT `score1`/`score2`.
The `/api/matches` endpoint returns the raw matches array from that feed.

### Card data
The live feed has no card data. Yellow and red cards are manually tracked in `CARD_DATA`
in `static/index.html`, keyed as `"team1|team2"`. Update this object after each matchday.

### Fallback
If `/api/matches` fails or returns no scored matches, the frontend falls back to
`FALLBACK` — a hardcoded array of results through Jun 18. Keep this up to date too.

### Team name aliases
The feed uses inconsistent names (e.g. "Czech Republic" vs "Czechia", "Korea Republic" vs
"South Korea"). The `ALIASES` object in index.html normalises these. Add new ones as needed.

## Adding new results (manual update workflow)
1. After each matchday, update `CARD_DATA` in index.html with yellow/red card counts.
2. Update `FALLBACK` in index.html with the new scores.
3. The live scores come automatically from the openfootball feed — no code change needed
   for goals/results, only for cards.

## Nginx config (same server as vlad.groupcaliber.ai)
Add a new server block:
```nginx
server {
    listen 80;
    server_name football.groupcaliber.ai;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name football.groupcaliber.ai;
    # ssl_certificate / ssl_certificate_key — same wildcard cert as vlad subdomain
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Deployment checklist
- [ ] `pip install -r requirements.txt` on the server
- [ ] `uvicorn server:app --host 0.0.0.0 --port 8001` running (or systemd service)
- [ ] Nginx config added and reloaded (`nginx -t && systemctl reload nginx`)
- [ ] DNS: `football.groupcaliber.ai` A record → same server IP as `vlad.groupcaliber.ai`
- [ ] SSL: wildcard cert `*.groupcaliber.ai` covers this subdomain automatically

## No auth needed
This is a fun internal tool with no sensitive data. No login required.
