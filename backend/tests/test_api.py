import importlib
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
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "infragym_http_requests_total" in response.text
