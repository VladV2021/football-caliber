from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import base64
import json
import os
import io
import re
import time
import zipfile
import xml.etree.ElementTree as ET

app = FastAPI()

GITHUB_API = "https://api.github.com/repos/openfootball/worldcup.json/contents/2026/worldcup.json"
GITHUB_RAW = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

# Dropbox-hosted "Card stats.xlsx" — provided via env var so the public repo
# never contains the link. Edit the spreadsheet in Dropbox and the change shows
# up here within CARD_CACHE_TTL seconds. No redeploy needed.
CARD_SHEET_URL = os.environ.get("CARD_SHEET_URL", "").strip()
CARD_CACHE_TTL = 60  # seconds
_card_cache = {"ts": 0.0, "data": None}

XL_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


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


def _direct_download_url(url: str) -> str:
    """Normalise a Dropbox share link to a direct-download URL (dl=1)."""
    if "dl=0" in url:
        return url.replace("dl=0", "dl=1")
    if "dl=1" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}dl=1"


def _col_letter(ref: str) -> str:
    m = re.match(r"([A-Z]+)", ref or "")
    return m.group(1) if m else ""


def _parse_card_xlsx(blob: bytes) -> dict:
    """Parse 'Card stats.xlsx' into {"Team1|Team2": {yc1,rc1,yc2,rc2}}.
    Columns are matched by header name, so column order can change freely."""
    z = zipfile.ZipFile(io.BytesIO(blob))

    # shared strings table (most cell text lives here)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{XL_NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{XL_NS}t")))

    sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
    if not sheets:
        return {}
    root = ET.fromstring(z.read(sheets[0]))

    def cell_value(c):
        t = c.get("t")
        v = c.find(f"{XL_NS}v")
        if v is not None and v.text is not None:
            return shared[int(v.text)] if t == "s" else v.text
        isv = c.find(f"{XL_NS}is")
        if isv is not None:
            return "".join(x.text or "" for x in isv.iter(f"{XL_NS}t"))
        return ""

    rows = []
    for row in root.iter(f"{XL_NS}row"):
        cells = {}
        for c in row.findall(f"{XL_NS}c"):
            cells[_col_letter(c.get("r", ""))] = cell_value(c)
        if cells:
            rows.append(cells)
    if not rows:
        return {}

    header = {v.strip(): col for col, v in rows[0].items() if v and v.strip()}
    needed = ["Team1", "YC_Team1", "RC_Team1", "Team2", "YC_Team2", "RC_Team2"]
    if not all(k in header for k in needed):
        raise ValueError(f"Spreadsheet missing expected columns. Found: {list(header)}")

    def num(cells, key):
        raw = (cells.get(header[key], "") or "").strip()
        try:
            return int(float(raw))
        except ValueError:
            return 0

    out = {}
    for cells in rows[1:]:
        t1 = (cells.get(header["Team1"], "") or "").strip()
        t2 = (cells.get(header["Team2"], "") or "").strip()
        if not t1 or not t2:
            continue
        out[f"{t1}|{t2}"] = {
            "yc1": num(cells, "YC_Team1"),
            "rc1": num(cells, "RC_Team1"),
            "yc2": num(cells, "YC_Team2"),
            "rc2": num(cells, "RC_Team2"),
        }
    return out


@app.get("/api/cards")
async def get_cards():
    """Serve manually-tracked yellow/red card data from the Dropbox 'Card stats.xlsx'.
    Cached for CARD_CACHE_TTL seconds. Returns ok=False (frontend keeps its built-in
    fallback) if the URL is unset or the fetch/parse fails."""
    if not CARD_SHEET_URL:
        return {"ok": False, "error": "CARD_SHEET_URL not configured", "cards": {}}

    now = time.time()
    if _card_cache["data"] is not None and (now - _card_cache["ts"]) < CARD_CACHE_TTL:
        return {"ok": True, "source": "cache", "cards": _card_cache["data"],
                "count": len(_card_cache["data"])}

    try:
        url = _direct_download_url(CARD_SHEET_URL)
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "football-caliber/1.0"})
        if r.status_code != 200 or r.content[:2] != b"PK":
            raise ValueError(f"Unexpected response (status {r.status_code})")
        cards = _parse_card_xlsx(r.content)
        _card_cache["data"] = cards
        _card_cache["ts"] = now
        return {"ok": True, "source": "dropbox-xlsx", "cards": cards, "count": len(cards)}
    except Exception as e:
        # Serve stale cache if we have one, otherwise let the frontend fall back.
        if _card_cache["data"] is not None:
            return {"ok": True, "source": "stale-cache", "cards": _card_cache["data"],
                    "count": len(_card_cache["data"]), "warning": str(e)}
        return {"ok": False, "error": str(e), "cards": {}}


@app.get("/health")
async def health():
    return {"status": "ok"}

# Serve the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")
