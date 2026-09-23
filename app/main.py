from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))
STATIC_DIR = Path(__file__).parent / "static"
started = time.monotonic()


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
        CREATE INDEX IF NOT EXISTS idx_material_code ON materials(code);
        CREATE INDEX IF NOT EXISTS idx_project_material ON projects(material_id);
        """)
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


mcp = FastMCP("Konverta Plastics Knowledge Base", instructions="Use these tools to look up the curated plastics recycling knowledge base. Always surface recorded safety notes and source limitations; do not invent compatibility or processing claims.")


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Konverta Plastics KB", version=APP_VERSION, lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app())
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


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
