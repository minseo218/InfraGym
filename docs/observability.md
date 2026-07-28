# InfraGym Observability

InfraGym exposes two deliberately separate classes of telemetry:

1. **Real platform telemetry** measures the FastAPI scenario engine itself:
   request throughput, status codes, latency, in-flight work, process/runtime
   metrics, and persisted SQLite training state.
2. **Logical scenario telemetry** represents the enterprise-scale system under
   investigation. These values change with the scenario stage without requiring
   millions of users or a large Kubernetes cluster on the host.

This distinction lets the stack run on a Mac mini while preserving the same
investigation loop used in a real incident.

## Signal flow

```text
FastAPI /metrics ────────────────→ Prometheus ──→ recording and alert rules
       │                                │
       └─ JSON stdout → Docker → Alloy  │
                                     │  │
                                     ↓  ↓
                                    Loki → Grafana
```

Grafana opens the provisioned **InfraGym Incident Operations** dashboard by
default.

## Metric catalog

### Real API RED metrics

| Metric | Purpose |
| --- | --- |
| `infragym_http_requests_total` | Requests by method, route template, and status |
| `infragym_http_request_duration_seconds` | Request-latency histogram |
| `infragym_http_requests_in_flight` | Concurrent request gauge |
| `infragym:http_request_rate5m` | Five-minute request-rate recording rule |
| `infragym:http_error_ratio5m` | Five-minute API 5xx ratio |
| `infragym:http_p95_latency_seconds5m` | Five-minute API p95 latency |
| `infragym:error_budget_burn_rate5m` | API burn rate against the 99.9% SLO |

HTTP metrics use route templates such as
`/api/v1/sessions/{session_id}`. Session IDs and request paths are not labels,
preventing unbounded time-series cardinality.

### Training-domain metrics

| Metric | Purpose |
| --- | --- |
| `infragym_sessions_created_total` | Sessions created during the process lifetime |
| `infragym_commands_total` | Commands grouped by bounded evidence type |
| `infragym_mitigations_total` | Accepted and rejected mitigation attempts |
| `infragym_sessions_completed_total` | Completed debriefs |
| `infragym_final_score` | Final-score histogram |
| `infragym_training_mttr_seconds` | Training MTTR histogram |
| `infragym_persisted_sessions` | SQLite session counts by status |
| `infragym_persisted_commands` | SQLite command-history count |

### Logical incident metrics

| Metric | Purpose |
| --- | --- |
| `infragym_scenario_stage` | 0 baseline, 1 surge, 2 pool exhaustion, 3 retry storm, 4 recovery |
| `infragym_scenario_request_rate_rps` | Simulated production request rate |
| `infragym_scenario_p95_latency_seconds` | Simulated production p95 latency |
| `infragym_scenario_error_ratio` | Simulated production 5xx ratio |
| `infragym_scenario_db_pool_utilization_ratio` | Simulated DB pool pressure |
| `infragym_scenario_retry_amplification` | Simulated downstream retry amplification |

## SLO and alerts

The Phase 1 ticketing service uses:

- availability objective: **99.9%**
- latency objective: **p95 ≤ 500 ms**
- error budget: **0.1% failed requests**

Prometheus evaluates four alerts:

| Alert | Trigger | Duration | Severity |
| --- | --- | --- | --- |
| `InfraGymAPIDown` | API scrape target is down | 30 s | critical |
| `InfraGymScenarioLatencySLOBreach` | Logical p95 > 500 ms | 30 s | critical |
| `InfraGymScenarioErrorBudgetBurn` | Logical burn rate > 14.4x | 30 s | critical |
| `InfraGymDatabasePoolSaturated` | Logical pool utilization ≥ 95% | 30 s | warning |

The 30-second `for` duration is intentionally short for a training lab. A
production service should derive alert windows from its traffic volume,
reliability target, and multi-window burn-rate policy.

## Structured logs

Application events are one-line JSON documents with stable fields:

```json
{
  "timestamp": "2026-07-28T07:23:23.848178+00:00",
  "level": "info",
  "service": "infragym-scenario-engine",
  "event": "command_executed",
  "session_id": "…",
  "evidence_type": "metrics",
  "supported": true
}
```

Alloy discovers only containers carrying the
`infragym_observability=true` label, attaches Compose service metadata, and
ships the logs to Loki. Session IDs remain searchable log fields but are not
Loki stream labels.

Useful LogQL:

```logql
{platform="docker", service_name="backend"} | json
```

```logql
{platform="docker", service_name="backend"} |= "mitigation_rejected" | json
```

## Local resource bounds

- Prometheus retention: 7 days
- Loki retention: 7 days
- Docker log rotation: 10 MiB × 3 files per service
- Alloy positions: persisted in the `alloy-data` volume

## Verification

Validate rule syntax and alert behavior:

```bash
docker run --rm \
  -v "$PWD/observability/prometheus:/workspace:ro" \
  -w /workspace/tests \
  --entrypoint /bin/promtool \
  prom/prometheus:v2.54.1 \
  test rules infragym.test.yml
```

Validate the live end-to-end signal path:

```bash
python3 scripts/verify-observability.py --wait-for-alerts
```

The live check creates a retry-storm incident, waits for all three
scenario-specific alerts to fire, verifies Prometheus targets and rules,
queries the generated command logs from Loki, verifies Grafana provisioning,
applies mitigation, and confirms the recovery-stage metric.
