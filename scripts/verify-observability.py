#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BACKEND = "http://localhost:8000"
PROMETHEUS = "http://localhost:9090"
LOKI = "http://localhost:3100"
GRAFANA = "http://localhost:3002"
ALLOY = "http://localhost:12345"


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 5,
) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_for(name: str, predicate, timeout: float = 45, interval: float = 1) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                print(f"PASS  {name}")
                return value
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
            last_error = exc
        time.sleep(interval)
    suffix = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Timed out waiting for {name}{suffix}")


def prometheus_query(query: str) -> list[dict[str, Any]]:
    url = f"{PROMETHEUS}/api/v1/query?{urlencode({'query': query})}"
    payload = request_json(url)
    if payload["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload["data"]["result"]


def metric_value(query: str) -> float | None:
    result = prometheus_query(query)
    return float(result[0]["value"][1]) if result else None


def create_incident() -> str:
    session = request_json(f"{BACKEND}/api/v1/sessions", method="POST", payload={})
    session_id = session["id"]
    request_json(f"{BACKEND}/api/v1/sessions/{session_id}/advance", method="POST", payload={})
    request_json(f"{BACKEND}/api/v1/sessions/{session_id}/advance", method="POST", payload={})
    for command in (
        "kubectl top pods",
        "kubectl logs deploy/ticketing-api --tail=20",
        "ss -s",
    ):
        request_json(
            f"{BACKEND}/api/v1/sessions/{session_id}/commands",
            method="POST",
            payload={"command": command},
        )
    return session_id


def loki_has_command_log() -> bool:
    start = int((time.time() - 300) * 1_000_000_000)
    params = urlencode(
        {
            "query": '{platform="docker",service_name="backend"} |= "command_executed"',
            "start": str(start),
            "limit": "100",
            "direction": "backward",
        }
    )
    payload = request_json(f"{LOKI}/loki/api/v1/query_range?{params}")
    streams = payload.get("data", {}).get("result", [])
    return any(stream.get("values") for stream in streams)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the complete InfraGym observability loop.")
    parser.add_argument(
        "--wait-for-alerts",
        action="store_true",
        help="wait through the alert 'for' duration and require firing alerts",
    )
    args = parser.parse_args()

    try:
        wait_for(
            "FastAPI health",
            lambda: request_json(f"{BACKEND}/health").get("status") == "ok",
        )
        wait_for(
            "Prometheus readiness",
            lambda: urlopen(f"{PROMETHEUS}/-/ready", timeout=5).status == 200,
        )
        wait_for(
            "Loki readiness",
            lambda: urlopen(f"{LOKI}/ready", timeout=5).status == 200,
        )
        wait_for(
            "Grafana health",
            lambda: request_json(f"{GRAFANA}/api/health").get("database") == "ok",
        )
        wait_for(
            "Alloy UI",
            lambda: urlopen(ALLOY, timeout=5).status == 200,
        )

        session_id = create_incident()
        print(f"INFO  generated stage-3 incident session {session_id}")

        wait_for(
            "scenario stage metric reached retry storm",
            lambda: metric_value(
                'infragym_scenario_stage{scenario="ticketing-traffic-spike"}'
            )
            == 3,
        )
        wait_for(
            "database pool saturation metric",
            lambda: metric_value("infragym_scenario_db_pool_utilization_ratio") == 1,
        )
        wait_for(
            "Prometheus recording rules",
            lambda: len(request_json(f"{PROMETHEUS}/api/v1/rules")["data"]["groups"]) >= 2,
        )
        wait_for(
            "all scrape targets are up",
            lambda: metric_value(
                'min(up{job=~"infragym-api|prometheus|alloy"})'
            )
            == 1,
        )
        wait_for("structured backend logs reached Loki", loki_has_command_log)
        wait_for(
            "provisioned Grafana dashboard",
            lambda: request_json(
                f"{GRAFANA}/api/dashboards/uid/infragym-incident-ops"
            )["dashboard"]["title"]
            == "InfraGym Incident Operations",
        )
        wait_for(
            "Grafana datasources",
            lambda: {
                item["uid"] for item in request_json(f"{GRAFANA}/api/datasources")
            }
            >= {"prometheus", "loki"},
        )

        if args.wait_for_alerts:
            wait_for(
                "latency SLO alert firing",
                lambda: bool(
                    prometheus_query(
                        'ALERTS{alertname="InfraGymScenarioLatencySLOBreach",alertstate="firing"}'
                    )
                ),
                timeout=60,
            )
            wait_for(
                "error-budget alert firing",
                lambda: bool(
                    prometheus_query(
                        'ALERTS{alertname="InfraGymScenarioErrorBudgetBurn",alertstate="firing"}'
                    )
                ),
            )
            wait_for(
                "database pool alert firing",
                lambda: bool(
                    prometheus_query(
                        'ALERTS{alertname="InfraGymDatabasePoolSaturated",alertstate="firing"}'
                    )
                ),
            )

        recovered = request_json(
            f"{BACKEND}/api/v1/sessions/{session_id}/mitigate",
            method="POST",
            payload={},
        )
        if recovered["stage"] != 4 or recovered["status"] != "recovered":
            raise RuntimeError(f"Mitigation did not recover the scenario: {recovered}")
        wait_for(
            "recovery reflected in metrics",
            lambda: metric_value("infragym_scenario_stage") == 4,
        )

        print("PASS  complete metrics, logs, alerts, dashboard, and recovery observability loop")
        return 0
    except (HTTPError, URLError, RuntimeError, TimeoutError, KeyError) as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
