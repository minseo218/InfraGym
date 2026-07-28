# InfraGym

> Train like a Real Systems Engineer.

InfraGym is a scenario-driven AI infrastructure training platform for Systems
Engineers, SREs, DevOps engineers, AI Platform Engineers, and GPU Infrastructure
Engineers. It combines a small real environment with a large logical
environment so realistic operational practice can run on a Mac mini.

## Phase 1 — Ticketing Traffic Spike

Phase 1 deliberately implements one complete learning loop before adding more
systems:

- timed incident progression from traffic surge to retry storm
- live RPS, p95 latency, 5xx rate, and database-pool telemetry
- service topology and incident timeline
- scenario-aware virtual terminal with mock `kubectl`, logs, events, sockets,
  and database-pool output
- evidence-based investigation checklist
- guarded mitigation, recovery state, and a 100-point score
- responsive desktop and mobile workspace

The virtual terminal never runs commands on the host machine or a real cluster.

## Run

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Open the local URL printed by the development server.

## Test

```bash
npm test
```

This creates a production build and verifies that the InfraGym workspace is
server-rendered without starter content.

## MVP roadmap

### Phase 2 — Linux Disk Full

- log-rotation failure → disk exhaustion → app failure
- `df`, `du`, `lsof`, `journalctl`, and `systemctl` scenario outputs
- root-cause and recovery scoring

### Phase 3 — GPU XID 79

- GPU node degradation → XID 79 → NCCL timeout → training-job failure
- `nvidia-smi`, `dcgmi`, Kubernetes events, and GPU-topology investigation
- drain, quarantine, replacement, and recovery decisions

## Product direction

Later milestones add FastAPI scenario orchestration, SQLite persistence, Docker
Compose, kind, Prometheus, Grafana, Loki, interview mode, capacity planning,
architecture decisions, automation exercises, and the broader scenario
catalog. The product will preserve the rule that each phase ships with an
implementation, tests, and runnable instructions.

## Stack

- React + TypeScript
- vinext / Cloudflare-compatible runtime
- CSS-native real-time telemetry UI
- Future phases: Python, FastAPI, SQLite, Docker, kind, Kubernetes,
  Prometheus, Grafana, and Loki

## Positioning

Built for anyone who wants to become a world-class Systems Engineer or SRE,
including candidates preparing for operational roles at Google, NVIDIA,
CoreWeave, Datadog, AWS, Microsoft, Toss, Lambda, Crusoe, and OpenAI.
