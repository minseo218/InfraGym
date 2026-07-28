import importlib
import json
import logging
import os

from fastapi.testclient import TestClient


def build_client(tmp_path):
    os.environ["INFRAGYM_DB_PATH"] = str(tmp_path / "test.db")
    from app import database, main

    importlib.reload(database)
    importlib.reload(main)
    return TestClient(main.app)


def test_complete_incident_learning_loop(tmp_path):
    with build_client(tmp_path) as client:
        created = client.post("/api/v1/sessions")
        assert created.status_code == 201
        session_id = created.json()["id"]
        assert created.json()["stage"] == 1

        client.post(f"/api/v1/sessions/{session_id}/advance")
        client.post(f"/api/v1/sessions/{session_id}/advance")

        for command in (
            "kubectl top pods",
            "kubectl logs deploy/ticketing-api --tail=20",
            "ss -s",
        ):
            response = client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json={"command": command},
            )
            assert response.status_code == 200

        mitigation = client.post(f"/api/v1/sessions/{session_id}/mitigate")
        assert mitigation.status_code == 200
        assert mitigation.json()["stage"] == 4
        assert mitigation.json()["status"] == "recovered"

        report = client.post(
            f"/api/v1/sessions/{session_id}/complete",
            json={
                "root_cause": "Traffic surge exhausted the database connection pool and retries amplified load.",
                "mitigation": "Cap retries with backoff, scale API replicas, and verify latency recovery.",
                "prevention": "Load test capacity, alert on SLO burn, and set retry and pool budgets.",
            },
        )
        assert report.status_code == 200
        assert report.json()["score"] >= 90
        assert "mttr_seconds" in report.json()


def test_mitigation_requires_evidence(tmp_path):
    with build_client(tmp_path) as client:
        session_id = client.post("/api/v1/sessions").json()["id"]
        response = client.post(f"/api/v1/sessions/{session_id}/mitigate")
        assert response.status_code == 409


def test_metrics_endpoint(tmp_path):
    with build_client(tmp_path) as client:
        session_id = client.post("/api/v1/sessions").json()["id"]
        client.post(f"/api/v1/sessions/{session_id}/advance")
        client.post(
            f"/api/v1/sessions/{session_id}/commands",
            json={"command": "kubectl top pods"},
        )
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "infragym_http_requests_total" in response.text
        assert 'route="/api/v1/sessions"' in response.text
        assert 'status_code="201"' in response.text
        assert (
            'infragym_scenario_stage{scenario="ticketing-traffic-spike"} 2.0'
            in response.text
        )
        assert (
            'infragym_scenario_db_pool_utilization_ratio'
            '{scenario="ticketing-traffic-spike"} 1.0'
            in response.text
        )
        assert 'infragym_commands_total{evidence_type="metrics"}' in response.text
        assert "infragym_http_request_duration_seconds_bucket" in response.text
        assert "infragym_persisted_sessions{status=\"active\"} 1.0" in response.text


def test_application_logs_are_structured_json():
    from app.observability import JsonFormatter

    record = logging.LogRecord(
        name="infragym",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="scenario_started",
        args=(),
        exc_info=None,
    )
    record.event = "scenario_started"
    record.fields = {"session_id": "session-123", "stage": 1}

    payload = json.loads(JsonFormatter().format(record))

    assert payload["service"] == "infragym-scenario-engine"
    assert payload["event"] == "scenario_started"
    assert payload["session_id"] == "session-123"
    assert payload["stage"] == 1
