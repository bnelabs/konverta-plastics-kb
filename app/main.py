from __future__ import annotations

import asyncio
import csv
import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import jwt
import uvicorn
from pydantic import BaseModel, Field, field_validator

try:  # `python -m app.main` / `uvicorn app.main:app`
    from app.curation import import_material_rows, parse_csv_rows, parse_json_rows, MATERIAL_COLUMNS, validate_material_row, material_row_values
except ModuleNotFoundError:  # pragma: no cover - `python app/main.py`
    from curation import import_material_rows, parse_csv_rows, parse_json_rows, MATERIAL_COLUMNS, validate_material_row, material_row_values

APP_VERSION = os.getenv("APP_VERSION", "0.5.1")
DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))
STATIC_DIR = Path(__file__).parent / "static"
started = time.monotonic()
access_team = os.getenv("CF_ACCESS_TEAM_DOMAIN", "").rstrip("/")
access_aud = os.getenv("CF_ACCESS_AUD", "")
access_email = os.getenv("CF_ACCESS_EMAIL", "baris@konverta.eu").strip().lower()
jwks_client = jwt.PyJWKClient(f"{access_team}/cdn-cgi/access/certs", cache_jwk_set=True, lifespan=3600) if access_team else None


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=8)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=8000")
    return con


def ensure_schema() -> None:
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS materials (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL, common_uses TEXT, melt_temp_c TEXT,
          density_g_cm3 REAL, toxicity_level TEXT, recyclability TEXT, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS processes (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          description TEXT, equipment_needed TEXT, safety_precautions TEXT
        );
        CREATE TABLE IF NOT EXISTS material_processes (
          material_id INTEGER NOT NULL REFERENCES materials(id),
          process_id INTEGER NOT NULL REFERENCES processes(id),
          suitability_rating TEXT, notes TEXT,
          UNIQUE(material_id, process_id)
        );
        CREATE TABLE IF NOT EXISTS compatibility (
          material_a_id INTEGER NOT NULL REFERENCES materials(id),
          material_b_id INTEGER NOT NULL REFERENCES materials(id),
          compatibility_status TEXT NOT NULL, description TEXT,
          UNIQUE(material_a_id, material_b_id)
        );
        CREATE TABLE IF NOT EXISTS projects (
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
          material_id INTEGER REFERENCES materials(id), process_id INTEGER REFERENCES processes(id),
          difficulty TEXT, description TEXT, instructions TEXT
        );
        CREATE TABLE IF NOT EXISTS kb_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
          entity_type TEXT NOT NULL, entity_id TEXT, actor TEXT NOT NULL DEFAULT 'system',
          details TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS contamination (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          contaminant_name TEXT NOT NULL,
          material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
          impact_description TEXT NOT NULL,
          safety_notes TEXT NOT NULL,
          source_title TEXT NOT NULL,
          source_url TEXT NOT NULL,
          review_status TEXT NOT NULL DEFAULT 'needs_review'
        );
        CREATE INDEX IF NOT EXISTS idx_material_code ON materials(code);
        CREATE INDEX IF NOT EXISTS idx_project_material ON projects(material_id);
        CREATE INDEX IF NOT EXISTS idx_contamination_material ON contamination(material_id);
        CREATE INDEX IF NOT EXISTS idx_contamination_contaminant ON contamination(contaminant_name);
        """)
        material_columns = {r[1] for r in con.execute("PRAGMA table_info(materials)")}
        for column, definition in (("source_title", "TEXT"), ("source_url", "TEXT"), ("review_status", "TEXT NOT NULL DEFAULT 'needs_review'")):
            if column not in material_columns:
                con.execute(f"ALTER TABLE materials ADD COLUMN {column} {definition}")
        # Populate only a newly initialized database. Existing rows are preserved.
        if con.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0:
            legacy = Path("/app/legacy-seed.sqlite3")
            if legacy.exists():
                old = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
                old.row_factory = sqlite3.Row
                for table in ("materials", "processes", "material_processes", "compatibility", "projects"):
                    cols = [r[1] for r in old.execute(f"PRAGMA table_info({table})")]
                    rows = old.execute(f"SELECT * FROM {table}").fetchall()
                    if rows:
                        marks = ",".join("?" for _ in cols)
                        con.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks})", [tuple(r) for r in rows])
                old.close()
            else:
                seed_initial(con)
            con.execute("INSERT INTO kb_events(event,entity_type,details) VALUES('seeded','database','Initial plastics KB dataset')")
        # Sync curated datasets from repo CSVs on every startup if they are present.
        # This makes the live DB self-healing without requiring manual host imports.
        sync_curated_materials(con)
        sync_curated_contamination(con)


def sync_curated_materials(con: sqlite3.Connection) -> None:
    """Upsert materials from scripts/materials_curated.csv if the file exists."""
    repo_root = Path(__file__).resolve().parent.parent
    csv_path = repo_root / "scripts" / "materials_curated.csv"
    if not csv_path.exists():
        return
    # Ensure required columns exist
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            inserted = 0
            updated = 0
            for row in reader:
                errors = validate_material_row(row)
                if errors:
                    continue
                values = material_row_values(row)
                # Upsert by code
                cols = ", ".join(MATERIAL_COLUMNS)
                placeholders = ", ".join("?" for _ in MATERIAL_COLUMNS)
                update_cols = ", ".join(f"{c}=excluded.{c}" for c in MATERIAL_COLUMNS if c != "code")
                sql = f"""
                INSERT INTO materials ({cols}) VALUES ({placeholders})
                ON CONFLICT(code) DO UPDATE SET {update_cols}
                """
                cur = con.execute(sql, [values[c] for c in MATERIAL_COLUMNS])
                # SQLite rowcount for UPSERT is tricky; assume update if code existed
                # Detect existence
                # We'll just count as upserted
                if cur.rowcount == 0:
                    updated += 1
                else:
                    inserted += 1
        if inserted or updated:
            con.execute(
                "INSERT INTO kb_events(event,entity_type,actor,details) VALUES('synced','materials','system',?)",
                (f'curated materials sync from {csv_path.name}: {inserted} inserted/updated, {updated} updated',)
            )
    except Exception:
        # Fail silently to avoid breaking startup; sync is best-effort
        return


def sync_curated_contamination(con: sqlite3.Connection) -> None:
    """Seed contamination risks from scripts/contamination_seed.csv if empty."""
    repo_root = Path(__file__).resolve().parent.parent
    csv_path = repo_root / "scripts" / "contamination_seed.csv"
    if not csv_path.exists():
        return
    # Only seed if table is empty to avoid duplication
    if con.execute("SELECT COUNT(*) FROM contamination").fetchone()[0] > 0:
        # Table already has data; skip
        return
    try:
        # Cache material codes
        materials = {r["code"].upper(): r["id"] for r in con.execute("SELECT id, code FROM materials")}
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                contaminant_name = (row.get("contaminant_name") or "").strip()
                material_code = (row.get("material_code") or "").strip().upper()
                impact_description = (row.get("impact_description") or "").strip()
                safety_notes = (row.get("safety_notes") or "").strip()
                source_title = (row.get("source_title") or "").strip()
                source_url = (row.get("source_url") or "").strip()
                review_status = (row.get("review_status") or "needs_review").strip()
                if not (contaminant_name and material_code and impact_description and safety_notes and source_title and source_url.startswith("https://")):
                    continue
                material_id = materials.get(material_code)
                if not material_id:
                    continue
                con.execute(
                    """INSERT OR IGNORE INTO contamination
                       (contaminant_name, material_id, impact_description, safety_notes, source_title, source_url, review_status)
                       VALUES (?,?,?,?,?,?,?)""",
                    (contaminant_name, material_id, impact_description, safety_notes, source_title, source_url, review_status)
                )
        con.execute(
            "INSERT INTO kb_events(event,entity_type,actor,details) VALUES('seeded','contamination','system',?)",
            (f'contamination seed from {csv_path.name}',)
        )
    except Exception:
        return


def seed_initial(con: sqlite3.Connection) -> None:
    materials = [
      ("PET","Polyethylene Terephthalate","Water bottles, soft drink bottles, clamshell containers","250 - 260°C",1.38,"Low","High (Widely recycled)","Prone to moisture degradation if not dried before melting."),
      ("HDPE","High-Density Polyethylene","Milk jugs, detergent bottles, pipe fittings","130 - 135°C",0.95,"Low","High","Excellent for shredding and injection molding or compression."),
      ("PP","Polypropylene","Bottle caps, yogurt containers, straws, tupperware","160 - 170°C",0.90,"Low","Medium","Great fatigue resistance, popular in Precious Plastic machines."),
      ("LDPE","Low-Density Polyethylene","Plastic bags, squeeze bottles, shrink wrap","105 - 115°C",0.92,"Low","Low-Medium","Melts at low temperatures; tricky for rigid items, good for melting into sheets."),
      ("PVC","Polyvinyl Chloride","Pipes, siding, wire insulation","160 - 210°C",1.40,"High","Low","WARNING: Releases toxic hydrogen chloride gas when overheated or burned."),
      ("PS","Polystyrene","Disposable cutlery, CD cases, styrofoam","240°C",1.05,"Medium","Low","Brittle; dissolves easily in acetone (good for solvent welding/recycling).")]
    con.executemany("INSERT INTO materials(code,name,common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes) VALUES(?,?,?,?,?,?,?,?)", materials)
    processes = [("Shredding","Mechanical reduction into flakes or granules.","Shredder machine, sorting bins","Eye protection and dust control."),("Injection Molding","Melting and injecting plastic into a mold under pressure.","Injection machine, heater band, molds","Burn risk; ensure adequate ventilation."),("Compression Molding","Heating flakes inside a mold under mechanical pressure.","Heat press, metal molds","Control heat and pressure; use ventilation."),("Sheet Pressing","Pressing material between flat plates to create sheets.","Platen heat press, release sheets","Monitor temperature to prevent scorching.")]
    con.executemany("INSERT INTO processes(name,description,equipment_needed,safety_precautions) VALUES(?,?,?,?)", processes)
    mids = {r["code"]: r["id"] for r in con.execute("SELECT id,code FROM materials")}
    pids = {r["name"]: r["id"] for r in con.execute("SELECT id,name FROM processes")}
    con.executemany("INSERT INTO material_processes VALUES(?,?,?,?)", [(mids["HDPE"],pids["Shredding"],"Excellent","Shreds cleanly into uniform flakes."),(mids["HDPE"],pids["Injection Molding"],"Excellent","Flows well and fills molds easily."),(mids["PP"],pids["Shredding"],"Excellent","Very versatile for shredding."),(mids["PP"],pids["Injection Molding"],"Excellent","Commonly used in desktop injection."),(mids["PET"],pids["Sheet Pressing"],"Moderate","Must be thoroughly dried to prevent degradation."),(mids["PVC"],pids["Injection Molding"],"Dangerous","Thermal degradation releases corrosive gas; avoid without professional controls.")])
    con.executemany("INSERT INTO compatibility VALUES(?,?,?,?)", [(mids["HDPE"],mids["LDPE"],"Blends with additives","Similar polyolefin structure, but melting points differ."),(mids["HDPE"],mids["PP"],"Incompatible","Phase separation can reduce mechanical strength."),(mids["PET"],mids["PVC"],"Incompatible","PVC contamination harms PET recycling batches.")])
    con.executemany("INSERT INTO projects(title,material_id,process_id,difficulty,description,instructions) VALUES(?,?,?,?,?,?)", [("HDPE Carabiner / Clip",mids["HDPE"],pids["Injection Molding"],"Medium","Molding utility clips from recycled HDPE flakes.","Sort and wash; shred to flakes; dry; select a validated material-specific process and mold."),("PP Coaster / Tile",mids["PP"],pids["Sheet Pressing"],"Easy","Decorative coasters from sorted PP caps.","Sort and clean PP; arrange in a mold; use validated equipment settings; cool fully before finishing.")])


def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def search_materials(q: str, limit: int = 20) -> list[dict[str, Any]]:
    q = q.strip()
    with connect() as con:
        if q:
            pat = f"%{q}%"
            rows = con.execute("SELECT * FROM materials WHERE code LIKE ? OR name LIKE ? OR common_uses LIKE ? OR notes LIKE ? ORDER BY code LIMIT ?", (pat, pat, pat, pat, limit)).fetchall()
        else:
            rows = con.execute("SELECT * FROM materials ORDER BY code LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def material_detail(code: str) -> dict[str, Any] | None:
    code = code.upper().strip()
    with connect() as con:
        row = con.execute("SELECT * FROM materials WHERE code=?", (code,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["processes"] = [dict(r) for r in con.execute("SELECT p.name,p.description,p.equipment_needed,p.safety_precautions,mp.suitability_rating,mp.notes FROM material_processes mp JOIN processes p ON p.id=mp.process_id WHERE mp.material_id=? ORDER BY p.name", (row["id"],))]
        d["projects"] = [dict(r) for r in con.execute("SELECT title,difficulty,description,instructions FROM projects WHERE material_id=? ORDER BY title", (row["id"],))]
        d["sources"] = []
        return d


def get_processes() -> list[dict[str, Any]]:
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM processes ORDER BY name")]


def get_projects(q: str = "") -> list[dict[str, Any]]:
    with connect() as con:
        pat = f"%{q.strip()}%"
        rows = con.execute("SELECT pr.*,m.code material_code,p.name process_name FROM projects pr LEFT JOIN materials m ON m.id=pr.material_id LEFT JOIN processes p ON p.id=pr.process_id WHERE ?='' OR pr.title LIKE ? OR pr.description LIKE ? OR m.code LIKE ? ORDER BY pr.title LIMIT 100", (q.strip(),pat,pat,pat)).fetchall()
        return [dict(r) for r in rows]


def check_compatibility(a: str, b: str) -> dict[str, str] | None:
    with connect() as con:
        row = con.execute("""SELECT a.code material_a,b.code material_b,c.compatibility_status,c.description
          FROM compatibility c JOIN materials a ON a.id=c.material_a_id JOIN materials b ON b.id=c.material_b_id
          WHERE (a.code=? AND b.code=?) OR (a.code=? AND b.code=?)""", (a.upper(),b.upper(),b.upper(),a.upper())).fetchone()
        return dict(row) if row else None


def list_contamination_risks(material_code: str = "", contaminant_query: str = "", limit: int = 100) -> list[dict[str, Any]]:
    material_code = material_code.strip().upper()
    contaminant_query = contaminant_query.strip()
    with connect() as con:
        clauses = []
        params: list[Any] = []
        if material_code:
            clauses.append("m.code = ?")
            params.append(material_code)
        if contaminant_query:
            clauses.append("c.contaminant_name LIKE ?")
            params.append(f"%{contaminant_query}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
          SELECT c.id, c.contaminant_name, m.code AS material_code, m.name AS material_name,
                 c.impact_description, c.safety_notes, c.source_title, c.source_url, c.review_status
          FROM contamination c
          JOIN materials m ON m.id = c.material_id
          {where}
          ORDER BY m.code, c.contaminant_name
          LIMIT ?
        """
        params.append(limit)
        rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


mcp = FastMCP(
    "Konverta Plastics Knowledge Base",
    instructions="Use these tools to look up the curated plastics recycling knowledge base. Always surface recorded safety notes and source limitations; do not invent compatibility or processing claims.",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["plastics-kb-mcp.plastics-kb.svc.cluster.local:8001"],
    ),
)


@mcp.tool()
def search_plastics_knowledge(query: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """Search polymer materials by resin code, name, uses, or notes."""
    return search_materials(query, max(1, min(limit, 25)))


@mcp.tool()
def get_plastic_material(code: str) -> dict[str, Any] | dict[str, str]:
    """Get material properties, process suitability, safety notes, and projects by resin code (for example HDPE or PET)."""
    return material_detail(code) or {"error": f"No material found for {code}"}


@mcp.tool()
def list_recycling_processes() -> list[dict[str, Any]]:
    """List recycling and upcycling processes, equipment, and safety precautions."""
    return get_processes()


@mcp.tool()
def check_polymer_compatibility(material_a: str, material_b: str) -> dict[str, str]:
    """Look up a recorded blend compatibility rule. An unknown pair is explicitly returned as unknown."""
    return check_compatibility(material_a, material_b) or {"material_a": material_a.upper(), "material_b": material_b.upper(), "compatibility_status": "Unknown", "description": "No compatibility rule is recorded. Do not infer compatibility; verify with reliable technical sources and testing."}


@mcp.tool()
def search_contamination_risks(query: str = "", material_code: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Search recorded contamination risks by contaminant name or material code. Always surface safety notes and source citations; do not invent risks."""
    limit = max(1, min(int(limit), 100))
    return list_contamination_risks(material_code=material_code, contaminant_query=query, limit=limit)

mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Konverta Plastics KB", version=APP_VERSION, lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


class MaterialInput(BaseModel):
    code: str = Field(min_length=2, max_length=12)
    name: str = Field(min_length=2, max_length=160)
    common_uses: str = Field(default="", max_length=1000)
    melt_temp_c: str = Field(default="", max_length=100)
    density_g_cm3: float | None = Field(default=None, ge=0, le=100)
    toxicity_level: str = Field(default="Not rated", max_length=40)
    recyclability: str = Field(default="Not recorded", max_length=120)
    notes: str = Field(default="", max_length=3000)
    source_title: str = Field(min_length=2, max_length=240)
    source_url: str = Field(min_length=10, max_length=2048)
    review_status: str = Field(default="draft", pattern="^(draft|verified)$")

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.replace("-", "").isalnum():
            raise ValueError("Use a short resin code with letters, numbers, or hyphens")
        return value

    @field_validator("source_url")
    @classmethod
    def require_https_source(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("https://"):
            raise ValueError("Source URL must use https://")
        return value


# --- write rate limiting ---------------------------------------------------
# In-memory fixed window for write methods. Limits read per request so tests can
# shrink them via KB_RATE_LIMIT_MAX / KB_RATE_LIMIT_WINDOW. Keyed by the
# authenticated actor email when present, else by client host.
_RATE_LIMIT_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
rate_limit_buckets: dict[str, list[float]] = {}


def rate_limit_exceeded(key: str) -> float | None:
    """Record one hit for *key*; return retry-after seconds when over the limit."""
    maximum = int(os.getenv("KB_RATE_LIMIT_MAX", "30"))
    window = float(os.getenv("KB_RATE_LIMIT_WINDOW", "60"))
    now = time.monotonic()
    hits = rate_limit_buckets.setdefault(key, [])
    if hits and now - hits[0] >= window:
        hits.clear()
    if len(hits) >= maximum:
        return max(1.0, window - (now - hits[0]))
    hits.append(now)
    return None


def actor_of(request: Request) -> str:
    """Authenticated email stashed by the Cloudflare gate, else a dev fallback."""
    return getattr(request.state, "actor_email", None) or "local-dev"


# Declared BEFORE cloudflare_access_gate so it runs inside it (the gate sets
# request.state.actor_email first and unauthenticated requests never count).
@app.middleware("http")
async def write_rate_limit(request, call_next):
    if request.method in _RATE_LIMIT_METHODS and request.url.path != "/healthz":
        key = actor_of(request) if getattr(request.state, "actor_email", None) else (
            request.client.host if request.client else "unknown")
        retry_after = rate_limit_exceeded(key)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "Write rate limit exceeded; retry later"},
                headers={"Retry-After": str(int(retry_after))},
            )
    return await call_next(request)


@app.middleware("http")
async def cloudflare_access_gate(request, call_next):
    if request.url.path != "/healthz" and access_aud:
        token = request.headers.get("cf-access-jwt-assertion")
        if not token or jwks_client is None:
            return JSONResponse(status_code=401, content={"detail": "Cloudflare Access authentication required"})
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=access_aud, issuer=access_team)
            if str(claims.get("email", "")).lower() != access_email:
                return JSONResponse(status_code=403, content={"detail": "This account is not authorized"})
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Cloudflare Access authentication required"})
        request.state.actor_email = str(claims.get("email", "")).strip().lower() or None
    return await call_next(request)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def health() -> dict[str, str]:
    with connect() as con:
        con.execute("SELECT 1").fetchone()
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/v1/metrics")
def metrics() -> dict[str, Any]:
    with connect() as con:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("materials","processes","material_processes","compatibility","projects")}
        db_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        last_event = con.execute("SELECT created_at,event FROM kb_events ORDER BY id DESC LIMIT 1").fetchone()
    return {"version": APP_VERSION, "uptime_seconds": int(time.monotonic()-started), "database_bytes": db_bytes, "records": counts, "last_event": dict(last_event) if last_event else None}


@app.get("/api/v1/materials")
def materials(q: str = Query(default="", max_length=120), limit: int = Query(default=50, ge=1, le=100)) -> list[dict[str, Any]]:
    return search_materials(q, limit)


@app.get("/api/v1/materials/needs_review")
def materials_needs_review(limit: int = Query(default=50, ge=1, le=100)) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute("SELECT * FROM materials WHERE review_status != 'verified' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


BULK_MAX_ROWS = 10000
BULK_MAX_BYTES = 5_000_000


def _store_bulk_rows(rows: list[tuple[int, Any]], source_format: str, actor: str) -> dict[str, Any]:
    """Insert a validated batch on a worker thread so the event loop stays free."""
    con = connect()
    try:
        result = import_material_rows(con, rows, source_format=source_format, actor=actor)
        con.commit()
    finally:
        con.close()
    return result


@app.post("/api/v1/materials/bulk")
async def bulk_materials(request: Request) -> dict[str, Any]:
    """Import a CSV document or a JSON array of material rows with per-row validation.

    Registered before the /api/v1/materials/{code} routes so the literal path is
    never shadowed. Valid rows are inserted, invalid or duplicate codes are
    skipped and reported; a row without a valid source is never inserted.
    """
    raw = await request.body()
    if len(raw) > BULK_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Batch exceeds the {BULK_MAX_BYTES}-byte limit")
    try:
        document = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Request body must be UTF-8 encoded") from exc
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type in ("text/csv", "application/csv"):
        as_json = False
    elif content_type in ("application/json", "text/json"):
        as_json = True
    else:
        as_json = document.lstrip()[:1] in ("[", "{")
    try:
        rows = parse_json_rows(document) if as_json else parse_csv_rows(document)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(rows) > BULK_MAX_ROWS:
        raise HTTPException(status_code=413, detail=f"Batch exceeds the {BULK_MAX_ROWS}-row limit")
    return await run_in_threadpool(_store_bulk_rows, rows, "json" if as_json else "csv", actor_of(request))


@app.post("/api/v1/materials", status_code=201)
def create_material(payload: MaterialInput, request: Request) -> dict[str, Any]:
    values = payload.model_dump()
    with connect() as con:
        columns = ",".join(values)
        marks = ",".join("?" for _ in values)
        try:
            cur = con.execute(f"INSERT INTO materials ({columns}) VALUES ({marks})", list(values.values()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="A material with that resin code already exists") from exc
        material_id = cur.lastrowid
        con.execute("INSERT INTO kb_events(event,entity_type,entity_id,actor,details) VALUES('created','material',?,?,?)", (str(material_id), actor_of(request), json.dumps({"code": values["code"], "review_status": values["review_status"]})))
        return dict(con.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone())


@app.put("/api/v1/materials/{code}")
def update_material(code: str, payload: MaterialInput, request: Request) -> dict[str, Any]:
    values = payload.model_dump()
    with connect() as con:
        exists = con.execute("SELECT id FROM materials WHERE code=?", (code.upper(),)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Material not found")
        assignments = ",".join(f"{column}=?" for column in values)
        try:
            con.execute(f"UPDATE materials SET {assignments} WHERE id=?", [*values.values(), exists["id"]])
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="A material with that resin code already exists") from exc
        con.execute("INSERT INTO kb_events(event,entity_type,entity_id,actor,details) VALUES('updated','material',?,?,?)", (str(exists["id"]), actor_of(request), json.dumps({"code": values["code"], "review_status": values["review_status"]})))
        return dict(con.execute("SELECT * FROM materials WHERE id=?", (exists["id"],)).fetchone())


@app.get("/api/v1/materials/{code}")
def material(code: str) -> dict[str, Any]:
    result = material_detail(code)
    if result is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return result


@app.get("/api/v1/processes")
def processes() -> list[dict[str, Any]]:
    return get_processes()


@app.get("/api/v1/projects")
def projects(q: str = Query(default="", max_length=120)) -> list[dict[str, Any]]:
    return get_projects(q)


@app.get("/api/v1/compatibility")
def compatibility(material_a: str, material_b: str) -> dict[str, str]:
    return check_compatibility(material_a, material_b) or JSONResponse(status_code=404, content={"detail":"No recorded compatibility rule; treat as unknown."})


@app.get("/api/v1/contamination")
def contamination_list(
    material_code: str = Query(default="", max_length=20),
    contaminant: str = Query(default="", max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Read-only listing of contamination risks. Filters by material code and/or contaminant name substring."""
    return list_contamination_risks(material_code=material_code, contaminant_query=contaminant, limit=limit)


EVENT_FIELDS = "id,event,entity_type,entity_id,actor,details,created_at"


@app.get("/api/v1/events")
def kb_events(
    entity_type: str | None = Query(default=None, max_length=40),
    entity_id: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Audit log rows, newest first. Entity history for the frontend history view."""
    clauses: list[str] = []
    params: list[Any] = []
    if entity_type:
        clauses.append("entity_type=?")
        params.append(entity_type)
    if entity_id:
        clauses.append("entity_id=?")
        params.append(entity_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as con:
        rows = con.execute(f"SELECT {EVENT_FIELDS} FROM kb_events{where} ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
        return [dict(r) for r in rows]


class ProcessInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=3000)
    equipment_needed: str = Field(default="", max_length=1000)
    safety_precautions: str = Field(min_length=1, max_length=2000)

    @field_validator("safety_precautions")
    @classmethod
    def require_safety(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("safety_precautions must not be empty (safety-first)")
        return value


@app.post("/api/v1/processes", status_code=201)
def create_process(payload: ProcessInput, request: Request) -> dict[str, Any]:
    values = payload.model_dump()
    with connect() as con:
        cur = con.execute("INSERT INTO processes(name,description,equipment_needed,safety_precautions) VALUES(?,?,?,?)", (values["name"], values["description"], values["equipment_needed"], values["safety_precautions"]))
        process_id = cur.lastrowid
        con.execute("INSERT INTO kb_events(event,entity_type,entity_id,actor,details) VALUES('created','process',?,?,?)", (str(process_id), actor_of(request), json.dumps({"name": values["name"]})))
        return dict(con.execute("SELECT * FROM processes WHERE id=?", (process_id,)).fetchone())


@app.put("/api/v1/processes/{process_id}")
def update_process(process_id: int, payload: ProcessInput, request: Request) -> dict[str, Any]:
    values = payload.model_dump()
    with connect() as con:
        if not con.execute("SELECT id FROM processes WHERE id=?", (process_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Process not found")
        con.execute("UPDATE processes SET name=?,description=?,equipment_needed=?,safety_precautions=? WHERE id=?", (values["name"], values["description"], values["equipment_needed"], values["safety_precautions"], process_id))
        con.execute("INSERT INTO kb_events(event,entity_type,entity_id,actor,details) VALUES('updated','process',?,?,?)", (str(process_id), actor_of(request), json.dumps({"name": values["name"]})))
        return dict(con.execute("SELECT * FROM processes WHERE id=?", (process_id,)).fetchone())


COMPATIBILITY_STATUSES = ("Compatible", "Incompatible", "Blends with additives", "Conditional")


class CompatibilityInput(BaseModel):
    material_a: str = Field(min_length=1, max_length=12)
    material_b: str = Field(min_length=1, max_length=12)
    status: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=10, max_length=2000)


@app.post("/api/v1/compatibility", status_code=201)
def upsert_compatibility(payload: CompatibilityInput, request: Request) -> dict[str, Any]:
    """Record a source-backed compatibility rule; unknown pairs are never created implicitly."""
    if payload.status not in COMPATIBILITY_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(COMPATIBILITY_STATUSES)}")
    code_a, code_b = payload.material_a.strip().upper(), payload.material_b.strip().upper()
    if code_a == code_b:
        raise HTTPException(status_code=400, detail="material_a and material_b must be different materials")
    with connect() as con:
        ids = {r["code"]: r["id"] for r in con.execute("SELECT id,code FROM materials WHERE code IN (?,?)", (code_a, code_b))}
        missing = [code for code in (code_a, code_b) if code not in ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"Unknown material code(s): {', '.join(missing)}")
        first, second = sorted((ids[code_a], ids[code_b]))  # canonical order, one row per pair
        changed = bool(con.execute("SELECT 1 FROM compatibility WHERE material_a_id=? AND material_b_id=?", (first, second)).fetchone())
        con.execute(
            "INSERT INTO compatibility(material_a_id,material_b_id,compatibility_status,description) VALUES(?,?,?,?) "
            "ON CONFLICT(material_a_id, material_b_id) DO UPDATE SET compatibility_status=excluded.compatibility_status, description=excluded.description",
            (first, second, payload.status, payload.description),
        )
        con.execute(
            "INSERT INTO kb_events(event,entity_type,entity_id,actor,details) VALUES(?,'compatibility',?,?,?)",
            ("updated" if changed else "created", f"{first}:{second}", actor_of(request),
             json.dumps({"material_a": code_a, "material_b": code_b, "status": payload.status})),
        )
        row = con.execute("""SELECT a.code material_a,b.code material_b,c.compatibility_status,c.description
          FROM compatibility c JOIN materials a ON a.id=c.material_a_id JOIN materials b ON b.id=c.material_b_id
          WHERE c.material_a_id=? AND c.material_b_id=?""", (first, second)).fetchone()
        return dict(row)


async def serve() -> None:
    ensure_schema()
    async with mcp.session_manager.run():
        public = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, workers=1, lifespan="off", proxy_headers=True))
        private_mcp = uvicorn.Server(uvicorn.Config(mcp_http_app, host="0.0.0.0", port=8001, workers=1, lifespan="off", proxy_headers=False))
        await asyncio.gather(public.serve(), private_mcp.serve())


if __name__ == "__main__":
    asyncio.run(serve())
