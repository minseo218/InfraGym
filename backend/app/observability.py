from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

SERVICE_NAME = "infragym-scenario-engine"
SCENARIO = "ticketing-traffic-spike"


class JsonFormatter(logging.Formatter):
    """Render application events as one JSON document per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": SERVICE_NAME,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logger() -> logging.Logger:
    app_logger = logging.getLogger("infragym")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    if not any(getattr(handler, "_infragym_json", False) for handler in app_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._infragym_json = True  # type: ignore[attr-defined]
        app_logger.addHandler(handler)
    return app_logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    logger.info(
        event,
        extra={"event": event, "fields": fields},
        exc_info=exc_info,
    )


BUILD_INFO = Info("infragym_build", "InfraGym service build information.")
BUILD_INFO.info({"version": "0.3.0", "service": SERVICE_NAME})

HTTP_REQUESTS = Counter(
    "infragym_http_requests_total",
    "HTTP requests handled by the scenario engine.",
    ("method", "route", "status_code"),
)
HTTP_DURATION = Histogram(
    "infragym_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
HTTP_IN_FLIGHT = Gauge(
    "infragym_http_requests_in_flight",
    "HTTP requests currently being handled.",
    ("method",),
)

SESSIONS_CREATED = Counter(
    "infragym_sessions_created_total",
    "Training sessions created since process start.",
    ("scenario",),
)
COMMANDS = Counter(
    "infragym_commands_total",
    "Virtual terminal commands executed since process start.",
    ("evidence_type",),
)
MITIGATIONS = Counter(
    "infragym_mitigations_total",
    "Mitigation attempts since process start.",
    ("outcome",),
)
SESSIONS_COMPLETED = Counter(
    "infragym_sessions_completed_total",
    "Training sessions completed since process start.",
    ("scenario",),
)
FINAL_SCORE = Histogram(
    "infragym_final_score",
    "Final training-session score.",
    ("scenario",),
    buckets=(20, 40, 60, 70, 80, 90, 95, 100),
)
MTTR = Histogram(
    "infragym_training_mttr_seconds",
    "Elapsed time from scenario start to completed debrief.",
    ("scenario",),
    buckets=(30, 60, 120, 300, 600, 900, 1800, 3600),
)

PERSISTED_SESSIONS = Gauge(
    "infragym_persisted_sessions",
    "Sessions currently stored in SQLite by status.",
    ("status",),
)
PERSISTED_COMMANDS = Gauge(
    "infragym_persisted_commands",
    "Virtual terminal commands currently stored in SQLite.",
)

SCENARIO_STAGE = Gauge(
    "infragym_scenario_stage",
    "Current logical incident stage, from 0 (baseline) to 4 (recovered).",
    ("scenario",),
)
SCENARIO_RPS = Gauge(
    "infragym_scenario_request_rate_rps",
    "Logical service request rate for the active training scenario.",
    ("scenario",),
)
SCENARIO_P95_LATENCY = Gauge(
    "infragym_scenario_p95_latency_seconds",
    "Logical service p95 latency for the active training scenario.",
    ("scenario",),
)
SCENARIO_ERROR_RATIO = Gauge(
    "infragym_scenario_error_ratio",
    "Logical service 5xx ratio for the active training scenario.",
    ("scenario",),
)
SCENARIO_DB_POOL_UTILIZATION = Gauge(
    "infragym_scenario_db_pool_utilization_ratio",
    "Logical database connection-pool utilization for the active scenario.",
    ("scenario",),
)
SCENARIO_RETRY_AMPLIFICATION = Gauge(
    "infragym_scenario_retry_amplification",
    "Logical downstream request amplification caused by retries.",
    ("scenario",),
)

SCENARIO_SIGNALS = {
    0: (820, 0.184, 0.0012, 0.44, 1.0),
    1: (12_400, 0.438, 0.0081, 0.72, 1.0),
    2: (14_800, 1.840, 0.0390, 1.00, 1.0),
    3: (21_300, 4.820, 0.1280, 1.00, 3.0),
    4: (9_600, 0.312, 0.0034, 0.61, 1.0),
}


def update_scenario_signals(stage: int) -> None:
    safe_stage = stage if stage in SCENARIO_SIGNALS else 0
    rps, latency, error_ratio, pool_utilization, retry_amplification = SCENARIO_SIGNALS[
        safe_stage
    ]
    SCENARIO_STAGE.labels(SCENARIO).set(safe_stage)
    SCENARIO_RPS.labels(SCENARIO).set(rps)
    SCENARIO_P95_LATENCY.labels(SCENARIO).set(latency)
    SCENARIO_ERROR_RATIO.labels(SCENARIO).set(error_ratio)
    SCENARIO_DB_POOL_UTILIZATION.labels(SCENARIO).set(pool_utilization)
    SCENARIO_RETRY_AMPLIFICATION.labels(SCENARIO).set(retry_amplification)


def update_persisted_counts(session_counts: dict[str, int], command_count: int) -> None:
    for status in ("active", "recovered", "completed"):
        PERSISTED_SESSIONS.labels(status).set(session_counts.get(status, 0))
    PERSISTED_COMMANDS.set(command_count)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


update_scenario_signals(0)
