from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import base64
import json
import os
from openpyxl import load_workbook

app = FastAPI()

GITHUB_API = "https://api.github.com/repos/openfootball/worldcup.json/contents/2026/worldcup.json"
GITHUB_RAW = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

# Yellow/red cards are maintained by hand in this spreadsheet, committed to the
# repo root. The server parses it once at startup. To publish new cards: update
# "Card stats.xlsx" on GitHub, then redeploy the app (DO App Platform has no
# auto-deploy, so the new file is only picked up on the next deploy/restart).
HERE = os.path.dirname(os.path.abspath(__file__))
CARD_FILE = os.path.join(HERE, "Card stats.xlsx")


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


def _num(v):
    """Coerce a spreadsheet cell to a non-negative int (blank/garbage -> 0)."""
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return 0


def _parse_card_xlsx(path: str) -> dict:
    """Parse 'Card stats.xlsx' into {"Team1|Team2": {yc1,rc1,yc2,rc2}}.
    Columns are matched by header name, so column order can change freely.
    Expected headers: Team1, YC_Team1, RC_Team1, Team2, YC_Team2, RC_Team2."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    try:
        header_row = next(rows)
    except StopIteration:
        return {}
    header = {str(h).strip(): i for i, h in enumerate(header_row) if h is not None}

    needed = ["Team1", "YC_Team1", "RC_Team1", "Team2", "YC_Team2", "RC_Team2"]
    missing = [k for k in needed if k not in header]
    if missing:
        raise ValueError(f"Spreadsheet missing columns {missing}. Found: {list(header)}")

    def cell(row, key):
        i = header[key]
        return row[i] if i < len(row) else None

    out = {}
    for row in rows:
        if row is None:
            continue
        t1 = cell(row, "Team1")
        t2 = cell(row, "Team2")
        t1 = str(t1).strip() if t1 is not None else ""
        t2 = str(t2).strip() if t2 is not None else ""
        if not t1 or not t2:
            continue
        out[f"{t1}|{t2}"] = {
            "yc1": _num(cell(row, "YC_Team1")),
            "rc1": _num(cell(row, "RC_Team1")),
            "yc2": _num(cell(row, "YC_Team2")),
            "rc2": _num(cell(row, "RC_Team2")),
        }
    wb.close()
    return out


def _load_cards():
    """Load card data from the bundled spreadsheet at startup. On any failure
    returns ({}, message); the frontend then keeps its built-in CARD_DATA fallback."""
    try:
        return _parse_card_xlsx(CARD_FILE), None
    except Exception as e:
        return {}, str(e)


_CARDS, _CARDS_ERR = _load_cards()


@app.get("/api/cards")
async def get_cards():
    """Serve manually-tracked yellow/red card data parsed from the committed
    'Card stats.xlsx' at startup."""
    if _CARDS:
        return {"ok": True, "source": "repo-file", "cards": _CARDS, "count": len(_CARDS)}
    return {"ok": False, "error": _CARDS_ERR or "No card data", "cards": {}}


@app.get("/health")
async def health():
    return {"status": "ok"}

# Serve the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")
