#!/usr/bin/env python3
"""Black-box verification for the running InfraGym Docker Compose stack."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any


ENDPOINTS = {
    "frontend": "http://localhost:3000/",
    "backend": "http://localhost:8000/health",
    "prometheus": "http://localhost:9090/-/ready",
    "loki": "http://localhost:3100/ready",
    "grafana": "http://localhost:3002/api/health",
}
API = "http://localhost:8000/api/v1"


def request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    expected: int = 200,
) -> tuple[int, bytes]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            code, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        code, body = error.code, error.read()
    if code != expected:
        raise AssertionError(f"{method} {url}: expected HTTP {expected}, got {code}: {body[:300]!r}")
    return code, body


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    expected: int = 200,
) -> dict[str, Any] | list[dict[str, Any]]:
    _, body = request(url, method=method, payload=payload, expected=expected)
    return json.loads(body)


def wait_for_stack(timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    pending = dict(ENDPOINTS)
    while pending and time.monotonic() < deadline:
        for name, url in list(pending.items()):
            try:
                request(url)
                del pending[name]
            except (AssertionError, OSError, urllib.error.URLError):
                pass
        if pending:
            time.sleep(2)
    if pending:
        raise AssertionError(f"services did not become ready: {', '.join(pending)}")
    print("PASS readiness: frontend, backend, Prometheus, Loki, Grafana")


def verify_scenario() -> str:
    created = request_json(f"{API}/sessions", method="POST", expected=201)
    assert isinstance(created, dict)
    session_id = str(created["id"])

    request(f"{API}/sessions/{session_id}/mitigate", method="POST", expected=409)
    request(
        f"{API}/sessions/{session_id}/commands",
        method="POST",
        payload={"command": ""},
        expected=422,
    )

    evidence: set[str] = set()
    commands = (
        "kubectl top pods",
        "kubectl logs deploy/ticketing-api --tail=20",
        "ss -s",
    )
    for command in commands:
        response = request_json(
            f"{API}/sessions/{session_id}/commands",
            method="POST",
            payload={"command": command},
        )
        assert isinstance(response, dict)
        evidence.update(response["evidence"])

    assert evidence == {"metrics", "logs", "network"}, evidence
    for _ in range(2):
        request_json(f"{API}/sessions/{session_id}/advance", method="POST")

    mitigated = request_json(f"{API}/sessions/{session_id}/mitigate", method="POST")
    assert isinstance(mitigated, dict)
    assert mitigated["status"] == "recovered"
    assert mitigated["stage"] == 4

    report = request_json(
        f"{API}/sessions/{session_id}/complete",
        method="POST",
        payload={
            "root_cause": (
                "Traffic surge exhausted the database connection pool and "
                "a retry storm amplified load."
            ),
            "mitigation": (
                "Capped retries with backoff, scaled replicas, and monitored "
                "latency during recovery."
            ),
            "prevention": (
                "Add capacity load tests, SLO alerts, and a strict retry "
                "budget with pool limits."
            ),
        },
    )
    assert isinstance(report, dict)
    assert report["score"] >= 90

    saved = request_json(f"{API}/sessions/{session_id}")
    assert isinstance(saved, dict)
    assert saved["status"] == "completed"
    assert len(saved["evidence"]) == 3
    print(
        "PASS scenario API: negative cases, evidence gate, mitigation, "
        f"debrief (score={report['score']})"
    )
    return session_id


def verify_sqlite(session_id: str) -> None:
    code = (
        "import json,sqlite3,sys;"
        "c=sqlite3.connect('/data/infragym.db');"
        "row=c.execute('SELECT status FROM sessions WHERE id=?',(sys.argv[1],)).fetchone();"
        "n=c.execute('SELECT count(*) FROM command_history WHERE session_id=?',"
        "(sys.argv[1],)).fetchone()[0];"
        "print(json.dumps({'status':row[0] if row else None,'commands':n}))"
    )
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-c", code, session_id],
        check=True,
        capture_output=True,
        text=True,
    )
    state = json.loads(result.stdout)
    assert state == {"status": "completed", "commands": 3}, state
    print("PASS SQLite: completed session and 3-command history stored in volume")


def verify_observability() -> None:
    targets = request_json("http://localhost:9090/api/v1/targets")
    assert isinstance(targets, dict)
    active = targets["data"]["activeTargets"]
    assert active and all(target["health"] == "up" for target in active), active

    query = urllib.parse.urlencode({"query": "infragym_http_requests_total"})
    metric = request_json(f"http://localhost:9090/api/v1/query?{query}")
    assert isinstance(metric, dict)
    assert metric["status"] == "success" and metric["data"]["result"]

    datasources = request_json("http://localhost:3002/api/datasources")
    assert isinstance(datasources, list)
    by_name = {source["name"]: source for source in datasources}
    assert set(by_name) >= {"Prometheus", "Loki"}
    for name in ("Prometheus", "Loki"):
        health = request_json(
            f"http://localhost:3002/api/datasources/uid/{by_name[name]['uid']}/health"
        )
        assert isinstance(health, dict)
        assert health["status"] == "OK", health

    build = request_json("http://localhost:3100/loki/api/v1/status/buildinfo")
    assert isinstance(build, dict)
    assert build["version"]
    print("PASS observability: scrape target, custom metric, Grafana datasources, Loki API")


def restart_and_verify(session_id: str) -> None:
    subprocess.run(["docker", "compose", "restart", "backend"], check=True)
    wait_for_stack()
    saved = request_json(f"{API}/sessions/{session_id}")
    assert isinstance(saved, dict)
    assert saved["status"] == "completed"
    report = request_json(f"{API}/sessions/{session_id}/report")
    assert isinstance(report, dict)
    assert report["score"] >= 90
    print("PASS recovery: backend restart preserved session and report")


def crash_and_verify(session_id: str) -> None:
    container_id = subprocess.run(
        ["docker", "compose", "ps", "-q", "backend"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    before = int(
        subprocess.run(
            ["docker", "inspect", "-f", "{{.RestartCount}}", container_id],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "sh", "-c", "kill -TERM 1"],
        check=True,
    )

    deadline = time.monotonic() + 60
    after = before
    while time.monotonic() < deadline:
        state = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} "
                "{{.RestartCount}}",
                container_id,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        if len(state) == 3:
            after = int(state[2])
            if state[:2] == ["running", "healthy"] and after > before:
                break
        time.sleep(2)
    else:
        raise AssertionError("backend did not automatically recover from process termination")

    report = request_json(f"{API}/sessions/{session_id}/report")
    assert isinstance(report, dict)
    assert report["score"] >= 90
    print(
        "PASS crash recovery: restart policy recovered backend "
        f"(restart count {before} -> {after}) and preserved report"
    )


def verify_concurrent_load() -> None:
    cases = (
        ("backend health", "GET", ENDPOINTS["backend"], 500, 25, 200),
        ("session creation", "POST", f"{API}/sessions", 60, 12, 201),
        ("frontend", "GET", ENDPOINTS["frontend"], 200, 20, 200),
    )
    for name, method, url, count, workers, expected in cases:
        def call(_: int) -> int:
            code, _ = request(url, method=method, expected=expected)
            return code

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(call, range(count)))
        statuses = Counter(results)
        assert statuses == {expected: count}, statuses
        print(
            f"PASS load: {name} requests={count} concurrency={workers} "
            f"elapsed={time.monotonic() - started:.2f}s"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--restart-backend",
        action="store_true",
        help="restart FastAPI and verify SQLite volume persistence",
    )
    parser.add_argument(
        "--crash-backend",
        action="store_true",
        help="terminate FastAPI PID 1 and verify automatic crash recovery",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="run bounded concurrent load against frontend and FastAPI",
    )
    args = parser.parse_args()

    wait_for_stack()
    session_id = verify_scenario()
    verify_sqlite(session_id)
    verify_observability()
    if args.load:
        verify_concurrent_load()
    if args.restart_backend:
        restart_and_verify(session_id)
    if args.crash_backend:
        crash_and_verify(session_id)
    print(f"ALL CHECKS PASSED session_id={session_id}")


if __name__ == "__main__":
    main()
