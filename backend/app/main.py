from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import connection, evidence_from_row, init_database
from .scenario import execute_command, grade_debrief, investigation_score, normalize_command

logger = logging.getLogger("infragym")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REQUESTS = 0
COMMANDS = 0
STARTED_AT = time.monotonic()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="InfraGym Scenario Engine",
    version="0.2.0",
    description="Persistent Phase 1 scenario engine for InfraGym.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_origin_regex=r"https://.*\.chatgpt\.site",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CommandRequest(BaseModel):
    command: Annotated[str, Field(min_length=1, max_length=240)]


class DebriefRequest(BaseModel):
    root_cause: Annotated[str, Field(min_length=12, max_length=2000)]
    mitigation: Annotated[str, Field(min_length=12, max_length=2000)]
    prevention: Annotated[str, Field(min_length=12, max_length=2000)]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def serialize_session(row) -> dict:
    evidence = evidence_from_row(row)
    return {
        "id": row["id"],
        "scenario": row["scenario"],
        "stage": row["stage"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "evidence": evidence,
        "score": row["score"],
        "report": json.loads(row["report"]) if row["report"] else None,
    }


def require_session(session_id: str):
    with connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@app.middleware("http")
async def count_requests(request, call_next):
    global REQUESTS
    REQUESTS += 1
    response = await call_next(request)
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "infragym-scenario-engine", "version": "0.2.0"}


@app.post("/api/v1/sessions", status_code=201)
def create_session() -> dict:
    session_id = str(uuid4())
    started_at = now_iso()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions(id, scenario, stage, status, started_at, evidence, score)
            VALUES (?, 'ticketing-traffic-spike', 1, 'active', ?, '[]', 12)
            """,
            (session_id, started_at),
        )
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    logger.info("scenario_started session_id=%s scenario=ticketing-traffic-spike", session_id)
    return serialize_session(row)


@app.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    return serialize_session(require_session(session_id))


@app.post("/api/v1/sessions/{session_id}/advance")
def advance_session(session_id: str) -> dict:
    row = require_session(session_id)
    if row["status"] != "active":
        return serialize_session(row)
    next_stage = min(3, int(row["stage"]) + 1)
    with connection() as conn:
        conn.execute("UPDATE sessions SET stage = ? WHERE id = ?", (next_stage, session_id))
        updated = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    logger.info("scenario_advanced session_id=%s stage=%s", session_id, next_stage)
    return serialize_session(updated)


@app.post("/api/v1/sessions/{session_id}/commands")
def run_command(session_id: str, payload: CommandRequest) -> dict:
    global COMMANDS
    row = require_session(session_id)
    normalized = normalize_command(payload.command)
    result = execute_command(normalized)
    evidence = evidence_from_row(row)
    if result.evidence and result.evidence not in evidence:
        evidence.append(result.evidence)
    score = investigation_score(evidence, row["status"] in ("recovered", "completed"))
    created_at = now_iso()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO command_history(session_id, command, output, evidence_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, normalized, result.output, result.evidence, created_at),
        )
        conn.execute(
            "UPDATE sessions SET evidence = ?, score = ? WHERE id = ?",
            (json.dumps(evidence), score, session_id),
        )
    COMMANDS += 1
    logger.info(
        "command_executed session_id=%s command=%r evidence=%s",
        session_id,
        normalized,
        result.evidence,
    )
    return {
        "command": normalized,
        "output": result.output,
        "evidence": evidence,
        "score": score,
    }


@app.post("/api/v1/sessions/{session_id}/mitigate")
def mitigate(session_id: str) -> dict:
    row = require_session(session_id)
    evidence = evidence_from_row(row)
    if len(evidence) < 3:
        raise HTTPException(status_code=409, detail="Collect at least three evidence types first")
    score = investigation_score(evidence, recovered=True)
    with connection() as conn:
        conn.execute(
            "UPDATE sessions SET stage = 4, status = 'recovered', score = ? WHERE id = ?",
            (score, session_id),
        )
        updated = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    logger.info("mitigation_applied session_id=%s score=%s", session_id, score)
    return {
        **serialize_session(updated),
        "output": (
            "Mitigation accepted.\n"
            "✓ Retry budget capped at 2 attempts\n"
            "✓ ticketing-api scaled 4 → 12\n"
            "✓ DB pool queue draining\n"
            "Service is recovering. Continue monitoring."
        ),
    }


@app.post("/api/v1/sessions/{session_id}/complete")
def complete_session(session_id: str, payload: DebriefRequest) -> dict:
    row = require_session(session_id)
    if row["status"] not in ("recovered", "completed"):
        raise HTTPException(status_code=409, detail="Recover the service before completing the debrief")
    written_score, breakdown, summary = grade_debrief(
        payload.root_cause, payload.mitigation, payload.prevention
    )
    final_score = min(100, int(row["score"]) + written_score)
    finished_at = now_iso()
    started = datetime.fromisoformat(row["started_at"])
    finished = datetime.fromisoformat(finished_at)
    mttr_seconds = max(0, int((finished - started).total_seconds()))
    report = {
        "score": final_score,
        "breakdown": {
            "investigation_and_recovery": int(row["score"]),
            **breakdown,
        },
        "mttr_seconds": mttr_seconds,
        "summary": summary,
    }
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'completed', finished_at = ?, score = ?,
                root_cause = ?, mitigation = ?, prevention = ?, report = ?
            WHERE id = ?
            """,
            (
                finished_at,
                final_score,
                payload.root_cause,
                payload.mitigation,
                payload.prevention,
                json.dumps(report),
                session_id,
            ),
        )
    logger.info("scenario_completed session_id=%s score=%s mttr=%s", session_id, final_score, mttr_seconds)
    return report


@app.get("/api/v1/sessions/{session_id}/report")
def get_report(session_id: str) -> dict:
    row = require_session(session_id)
    if not row["report"]:
        raise HTTPException(status_code=404, detail="Debrief has not been completed")
    return json.loads(row["report"])


@app.get("/metrics")
def metrics() -> Response:
    uptime = time.monotonic() - STARTED_AT
    payload = (
        "# HELP infragym_http_requests_total Total HTTP requests.\n"
        "# TYPE infragym_http_requests_total counter\n"
        f"infragym_http_requests_total {REQUESTS}\n"
        "# HELP infragym_commands_total Total virtual terminal commands.\n"
        "# TYPE infragym_commands_total counter\n"
        f"infragym_commands_total {COMMANDS}\n"
        "# HELP infragym_process_uptime_seconds Scenario engine uptime.\n"
        "# TYPE infragym_process_uptime_seconds gauge\n"
        f"infragym_process_uptime_seconds {uptime:.3f}\n"
    )
    return Response(content=payload, media_type="text/plain; version=0.0.4")
