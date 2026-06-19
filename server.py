from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import base64
import json

app = FastAPI()

GITHUB_API = "https://api.github.com/repos/openfootball/worldcup.json/contents/2026/worldcup.json"
GITHUB_RAW = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

@app.get("/api/matches")
async def get_matches():
    """Proxy the openfootball GitHub feed server-side — no CORS issues.
    Tries the Contents API first (structured JSON), falls back to raw URL."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Attempt 1: GitHub Contents API (base64-encoded JSON)
        try:
            r = await client.get(GITHUB_API, headers={"Accept": "application/vnd.github.v3+json"})
            if r.status_code == 200:
                meta = r.json()
                if "content" in meta:
                    raw = base64.b64decode(meta["content"].replace("\n", "")).decode("utf-8")
                    data = json.loads(raw)
                    return {"ok": True, "source": "github-api", "matches": data.get("matches", [])}
        except Exception:
            pass

        # Attempt 2: raw.githubusercontent.com
        try:
            r = await client.get(GITHUB_RAW)
            if r.status_code == 200:
                data = r.json()
                return {"ok": True, "source": "github-raw", "matches": data.get("matches", [])}
        except Exception:
            pass

    return {"ok": False, "error": "Both GitHub sources unavailable", "matches": []}

@app.get("/health")
async def health():
    return {"status": "ok"}

# Serve the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")
