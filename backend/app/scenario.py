from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    output: str
    evidence: str | None = None


COMMANDS: dict[str, CommandResult] = {
    "help": CommandResult(
        "AVAILABLE  kubectl get pods | kubectl top pods | "
        "kubectl logs deploy/ticketing-api --tail=20\n"
        "           kubectl get events --sort-by=.lastTimestamp | ss -s | db-pool"
    ),
    "kubectl get pods": CommandResult(
        "NAME                              READY   STATUS    RESTARTS   AGE\n"
        "ticketing-api-7cf858f9c8-2kmlp   1/1     Running   0          42m\n"
        "ticketing-api-7cf858f9c8-bvtrn   1/1     Running   0          42m\n"
        "ticketing-api-7cf858f9c8-q8d6s   1/1     Running   1          42m\n"
        "postgres-primary-0                1/1     Running   0          6d",
        "events",
    ),
    "kubectl top pods": CommandResult(
        "NAME                              CPU(cores)   MEMORY(bytes)\n"
        "ticketing-api-7cf858f9c8-2kmlp   948m         712Mi\n"
        "ticketing-api-7cf858f9c8-bvtrn   963m         705Mi\n"
        "ticketing-api-7cf858f9c8-q8d6s   991m         728Mi\n"
        "postgres-primary-0                1840m        3.8Gi",
        "metrics",
    ),
    "kubectl logs deploy/ticketing-api --tail=20": CommandResult(
        "20:03:16.904 WARN  db.pool — timeout after 2000ms active=100 idle=0 pending=1842\n"
        '20:03:16.912 ERROR booking — request failed cause="connection acquisition timeout"\n'
        "20:03:16.919 WARN  retry — attempt=3 backoff=25ms route=/reservations",
        "logs",
    ),
    "kubectl get events --sort-by=.lastTimestamp": CommandResult(
        "LAST SEEN   TYPE      REASON             OBJECT                    MESSAGE\n"
        "8s          Warning   Unhealthy          pod/ticketing-api-q8d6s   Readiness probe timeout\n"
        "19s         Warning   FailedGetMetric    hpa/ticketing-api          CPU metric delayed\n"
        "41s         Normal    ScalingReplicaSet  deploy/ticketing-api       Scaled from 3 to 4",
        "events",
    ),
    "ss -s": CommandResult(
        "Total: 18642\n"
        "TCP:   20184 (estab 18307, closed 1198, orphaned 14, timewait 1184)\n"
        "Transport Total     IP        IPv6\nTCP       18986     18901     85",
        "network",
    ),
    "db-pool": CommandResult(
        "db_pool_active 100\n"
        "db_pool_idle 0\n"
        "db_pool_pending 1842\n"
        "db_pool_acquire_timeout_total 6871\n"
        "configured_max 100",
        "metrics",
    ),
}


def normalize_command(command: str) -> str:
    return " ".join(command.strip().split())


def execute_command(command: str) -> CommandResult:
    normalized = normalize_command(command)
    result = COMMANDS.get(normalized)
    if result:
        return result
    binary = normalized.split(" ", 1)[0] if normalized else ""
    return CommandResult(
        f"bash: {binary}: command not available in this lab\n"
        "Try 'help' to view scenario commands."
    )


def investigation_score(evidence: list[str], recovered: bool = False) -> int:
    return min(60, 12 + len(set(evidence)) * 10 + (8 if recovered else 0))


def grade_debrief(root_cause: str, mitigation: str, prevention: str) -> tuple[int, dict[str, int], str]:
    root = root_cause.lower()
    fix = mitigation.lower()
    prevent = prevention.lower()

    root_points = sum(
        [
            7 if any(word in root for word in ("pool", "connection")) else 0,
            5 if any(word in root for word in ("retry", "amplif", "storm")) else 0,
            4 if any(word in root for word in ("traffic", "rps", "surge")) else 0,
        ]
    )
    mitigation_points = sum(
        [
            5 if any(word in fix for word in ("retry", "backoff", "circuit")) else 0,
            4 if any(word in fix for word in ("scale", "replica", "capacity")) else 0,
            3 if any(word in fix for word in ("monitor", "verify", "latency")) else 0,
        ]
    )
    prevention_points = sum(
        [
            5 if any(word in prevent for word in ("load test", "capacity", "forecast")) else 0,
            4 if any(word in prevent for word in ("slo", "alert", "dashboard")) else 0,
            3 if any(word in prevent for word in ("limit", "budget", "pool")) else 0,
        ]
    )
    breakdown = {
        "root_cause": min(16, root_points),
        "mitigation": min(12, mitigation_points),
        "prevention": min(12, prevention_points),
    }
    total = sum(breakdown.values())
    if total >= 34:
        summary = "Strong causal chain and operational follow-through."
    elif total >= 22:
        summary = "Good diagnosis. Make the retry amplification and verification steps more explicit."
    else:
        summary = "Connect the traffic surge, pool exhaustion, retries, and prevention controls."
    return total, breakdown, summary
