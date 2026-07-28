# InfraGym

> Train like a Real Systems Engineer.

InfraGym is a scenario-driven AI infrastructure training platform for Systems
Engineers, SREs, DevOps engineers, AI Platform Engineers, and GPU Infrastructure
Engineers. It combines a small real environment with a large logical
environment so realistic operational practice can run on a Mac mini.

## Phase 1 — Ticketing Traffic Spike

Phase 1 implements one complete learning loop before adding more systems:

- timed incident progression from traffic surge to retry storm
- live RPS, p95 latency, 5xx rate, and database-pool telemetry
- service topology and incident timeline
- scenario-aware virtual terminal with mock `kubectl`, logs, events, sockets,
  and database-pool output
- evidence-gated mitigation and recovery
- root-cause, mitigation, and prevention debrief
- persistent 100-point assessment with MTTR
- Prometheus metrics plus provisioned Grafana and Loki services
- responsive desktop and mobile workspace

The virtual terminal never runs commands on the host machine or a real cluster.

## Architecture

```text
React workspace
    │
    ├── FastAPI available → persistent scenario session
    │                         ├── SQLite command/evidence history
    │                         ├── scoring and incident report
    │                         └── Prometheus metrics
    │
    └── API unavailable → safe in-browser demo engine

Prometheus ──┐
Loki ────────┼── Grafana
FastAPI ─────┘
```

## Run the full Phase 1 stack

Requires Docker Desktop or another Docker Compose-compatible runtime.

```bash
cp .env.example .env.local
docker compose up --build -d
```

Services:

- InfraGym UI: `http://localhost:3000`
- FastAPI and API docs: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3002`
- Loki: `http://localhost:3100/ready`

SQLite, Prometheus, Loki, and Grafana data are stored in named Docker volumes.

Run the full black-box stack verification, including bounded concurrent load,
backend restart/crash recovery, and SQLite persistence:

```bash
python3 scripts/verify-docker-stack.py --load --restart-backend --crash-backend
```

Stop the stack without deleting saved training sessions:

```bash
docker compose down
```

## Run the UI-only demo

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Without a configured API, the UI automatically uses its safe scenario fallback.

## Test

Frontend:

```bash
npm test
```

Backend:

```bash
docker build --target test -t infragym-backend-test backend
docker run --rm infragym-backend-test
```

## Phase 1 API

- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/advance`
- `POST /api/v1/sessions/{session_id}/commands`
- `POST /api/v1/sessions/{session_id}/mitigate`
- `POST /api/v1/sessions/{session_id}/complete`
- `GET /api/v1/sessions/{session_id}/report`
- `GET /metrics`
- `GET /health`

## MVP roadmap

### Phase 2 — Linux Disk Full

- log-rotation failure → disk exhaustion → application failure
- `df`, `du`, `lsof`, `journalctl`, and `systemctl` scenario outputs
- root-cause and recovery scoring

### Phase 3 — GPU XID 79

- GPU node degradation → XID 79 → NCCL timeout → training-job failure
- `nvidia-smi`, `dcgmi`, Kubernetes events, and GPU-topology investigation
- drain, quarantine, replacement, and recovery decisions

## Stack

- React + TypeScript
- Python + FastAPI
- SQLite
- Docker Compose
- Prometheus + Grafana + Loki
- vinext / Cloudflare-compatible frontend runtime

## Positioning

Built for anyone who wants to become a world-class Systems Engineer or SRE,
including candidates preparing for operational roles at Google, NVIDIA,
CoreWeave, Datadog, AWS, Microsoft, Toss, Lambda, Crusoe, and OpenAI.
