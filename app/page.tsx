"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type Stage = 0 | 1 | 2 | 3 | 4;
type Evidence = "metrics" | "events" | "logs" | "network";

const stages = [
  { label: "Ready", detail: "Baseline traffic is stable. Launch when you are ready.", time: "19:58:00" },
  { label: "Traffic surge", detail: "Ticket sales opened. Request volume is climbing fast.", time: "20:00:08" },
  { label: "Pool saturation", detail: "Database connections hit the configured ceiling.", time: "20:01:42" },
  { label: "Retry storm", detail: "Client retries amplify load. Error budget burn is critical.", time: "20:03:17" },
  { label: "Recovering", detail: "Retries are capped and API capacity has been increased.", time: "20:06:31" },
] as const;

const metricSets = [
  { rps: "820", latency: "184 ms", errors: "0.12%", pool: "44%" },
  { rps: "12.4k", latency: "438 ms", errors: "0.81%", pool: "72%" },
  { rps: "14.8k", latency: "1.84 s", errors: "3.9%", pool: "100%" },
  { rps: "21.3k", latency: "4.82 s", errors: "12.8%", pool: "100%" },
  { rps: "9.6k", latency: "312 ms", errors: "0.34%", pool: "61%" },
] as const;

const timeline = [
  { stage: 1, time: "20:00:08", title: "Ticket sale opened", type: "info" },
  { stage: 1, time: "20:00:31", title: "RPS crossed 10k", type: "warn" },
  { stage: 2, time: "20:01:42", title: "DB pool saturation", type: "critical" },
  { stage: 3, time: "20:03:17", title: "Retry amplification detected", type: "critical" },
  { stage: 4, time: "20:05:04", title: "Mitigation applied", type: "success" },
] as const;

const quickCommands = [
  "kubectl get pods",
  "kubectl top pods",
  "kubectl logs deploy/ticketing-api --tail=20",
  "kubectl get events --sort-by=.lastTimestamp",
] as const;

const commandResponses: Record<string, { output: string; evidence?: Evidence }> = {
  help: {
    output:
      "AVAILABLE  kubectl get pods | kubectl top pods | kubectl logs deploy/ticketing-api --tail=20\n           kubectl get events --sort-by=.lastTimestamp | ss -s | db-pool",
  },
  "kubectl get pods": {
    evidence: "events",
    output:
      "NAME                              READY   STATUS    RESTARTS   AGE\nticketing-api-7cf858f9c8-2kmlp   1/1     Running   0          42m\nticketing-api-7cf858f9c8-bvtrn   1/1     Running   0          42m\nticketing-api-7cf858f9c8-q8d6s   1/1     Running   1          42m\npostgres-primary-0                1/1     Running   0          6d",
  },
  "kubectl top pods": {
    evidence: "metrics",
    output:
      "NAME                              CPU(cores)   MEMORY(bytes)\nticketing-api-7cf858f9c8-2kmlp   948m         712Mi\nticketing-api-7cf858f9c8-bvtrn   963m         705Mi\nticketing-api-7cf858f9c8-q8d6s   991m         728Mi\npostgres-primary-0                1840m        3.8Gi",
  },
  "kubectl logs deploy/ticketing-api --tail=20": {
    evidence: "logs",
    output:
      '20:03:16.904 WARN  db.pool — timeout after 2000ms active=100 idle=0 pending=1842\n20:03:16.912 ERROR booking — request failed cause="connection acquisition timeout"\n20:03:16.919 WARN  retry — attempt=3 backoff=25ms route=/reservations',
  },
  "kubectl get events --sort-by=.lastTimestamp": {
    evidence: "events",
    output:
      "LAST SEEN   TYPE      REASON             OBJECT                    MESSAGE\n8s          Warning   Unhealthy          pod/ticketing-api-q8d6s   Readiness probe timeout\n19s         Warning   FailedGetMetric    hpa/ticketing-api          CPU metric delayed\n41s         Normal    ScalingReplicaSet  deploy/ticketing-api       Scaled from 3 to 4",
  },
  "ss -s": {
    evidence: "network",
    output:
      "Total: 18642\nTCP:   20184 (estab 18307, closed 1198, orphaned 14, timewait 1184)\nTransport Total     IP        IPv6\nTCP       18986     18901     85",
  },
  "db-pool": {
    evidence: "metrics",
    output:
      "db_pool_active 100\ndb_pool_idle 0\ndb_pool_pending 1842\ndb_pool_acquire_timeout_total 6871\nconfigured_max 100",
  },
};

const evidenceItems: { key: Evidence; label: string; hint: string }[] = [
  { key: "metrics", label: "Validate the saturation", hint: "Check resource and pool metrics" },
  { key: "events", label: "Inspect workload state", hint: "Check pods and recent events" },
  { key: "logs", label: "Find the failure signature", hint: "Read application logs" },
  { key: "network", label: "Check amplification", hint: "Inspect connection pressure" },
];

function Sparkline({ hot = false, recovering = false }: { hot?: boolean; recovering?: boolean }) {
  const bars = recovering
    ? [82, 76, 70, 59, 51, 45, 39, 34, 31, 28, 26, 24]
    : hot
      ? [14, 19, 17, 26, 34, 31, 48, 55, 63, 78, 84, 96]
      : [31, 36, 29, 42, 38, 44, 39, 47, 43, 40, 46, 41];
  return (
    <div className="sparkline" aria-hidden="true">
      {bars.map((height, index) => <span key={index} style={{ height: `${height}%` }} />)}
    </div>
  );
}

export default function Home() {
  const [stage, setStage] = useState<Stage>(0);
  const [running, setRunning] = useState(false);
  const [command, setCommand] = useState("");
  const [history, setHistory] = useState([{ command: "scenario status", output: "ticketing-traffic-spike is ready. Type 'help' for available commands." }]);
  const [evidence, setEvidence] = useState<Set<Evidence>>(new Set());
  const [activePanel, setActivePanel] = useState<"terminal" | "runbook">("terminal");
  const terminalRef = useRef<HTMLDivElement>(null);

  const metrics = metricSets[stage];
  const recovered = stage === 4;
  const score = stage === 0 ? 0 : Math.min(100, 12 + evidence.size * 15 + (recovered ? 28 : 0));

  useEffect(() => {
    if (!running || stage === 0 || stage >= 3) return;
    const timer = window.setTimeout(() => setStage((current) => Math.min(3, current + 1) as Stage), 6200);
    return () => window.clearTimeout(timer);
  }, [running, stage]);

  useEffect(() => {
    terminalRef.current?.scrollTo({ top: terminalRef.current.scrollHeight, behavior: "smooth" });
  }, [history]);

  const visibleTimeline = useMemo(() => timeline.filter((item) => item.stage <= stage), [stage]);

  function launchIncident() {
    setStage(1);
    setRunning(true);
    setEvidence(new Set());
    setHistory([{ command: "scenario start ticketing-traffic-spike", output: "Scenario started. You are the incident commander.\nObjective: restore p95 latency below 500ms without losing confirmed bookings." }]);
  }

  function resetScenario() {
    setStage(0);
    setRunning(false);
    setEvidence(new Set());
    setHistory([{ command: "scenario status", output: "ticketing-traffic-spike is ready. Type 'help' for available commands." }]);
  }

  function runCommand(rawCommand: string) {
    const normalized = rawCommand.trim().replace(/\s+/g, " ");
    if (!normalized) return;
    const response = commandResponses[normalized] ?? { output: `bash: ${normalized.split(" ")[0]}: command not available in this lab\nTry 'help' to view scenario commands.` };
    setHistory((items) => [...items, { command: normalized, output: response.output }]);
    if (response.evidence) setEvidence((items) => new Set(items).add(response.evidence as Evidence));
    setCommand("");
  }

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    runCommand(command);
  }

  function applyMitigation() {
    if (evidence.size < 3 || stage < 2) return;
    setStage(4);
    setRunning(false);
    setHistory((items) => [...items, {
      command: "infragym mitigate --cap-retries --scale-api=12",
      output: "Mitigation accepted.\n✓ Retry budget capped at 2 attempts\n✓ ticketing-api scaled 4 → 12\n✓ DB pool queue draining\nService is recovering. Continue monitoring.",
    }]);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="InfraGym home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>InfraGym</span>
        </a>
        <div className="topbar-center"><span className="status-dot" />Lab environment online<span className="topbar-divider" /><span className="mono">ap-northeast-2</span></div>
        <div className="topbar-actions"><span className="phase-pill">PHASE 01</span><button className="icon-button" aria-label="Open notifications">2</button><span className="avatar">ME</span></div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-pulse" />Live incident training</div>
          <h1>Train like a real<br /><span>systems engineer.</span></h1>
          <p>Investigate a production-grade outage through real signals. Build the muscle memory to observe, decide, mitigate, and explain.</p>
        </div>
        <div className="scenario-brief">
          <div className="brief-topline"><span className="scenario-code">SCENARIO 01 / 03</span><span className="difficulty">INTERMEDIATE</span></div>
          <div className="scenario-heading"><div className="scenario-icon">T</div><div><span>Public Service · Ticketing</span><h2>Traffic Spike at 20:00</h2></div></div>
          <p>One million users arrive for a limited ticket sale. Keep bookings available while latency and retries cascade through the stack.</p>
          <div className="scenario-meta">
            <div><span>ENVIRONMENT</span><strong>24 nodes · 100 logical services</strong></div>
            <div><span>TARGET MTTR</span><strong>≤ 8 minutes</strong></div>
          </div>
          {stage === 0 ? (
            <button className="launch-button" onClick={launchIncident}>Launch incident<span>↗</span></button>
          ) : (
            <div className="live-controls"><div><span className={`live-dot ${recovered ? "recovered" : ""}`} />{recovered ? "Service recovering" : "Incident in progress"}</div><button onClick={resetScenario}>Reset lab</button></div>
          )}
        </div>
      </section>

      <section className="workspace" aria-label="Incident workspace">
        <div className="workspace-heading">
          <div><span className="section-kicker">LIVE WORKSPACE</span><h2>Ticketing production</h2></div>
          <div className="incident-clock"><span>{stages[stage].time} KST</span><strong>{stages[stage].label}</strong></div>
        </div>

        <div className="metrics-grid">
          <MetricCard label="REQUEST RATE" source="PROMQL" value={metrics.rps} unit="req/s" hot={stage >= 1 && !recovered} recovered={recovered} footerLeft="↑ 38.4%" footerRight="vs. 5m ago" />
          <MetricCard label="P95 LATENCY" source="SLO" value={metrics.latency} hot={stage >= 2 && !recovered} recovered={recovered} footerLeft="SLO ≤ 500 ms" footerRight={stage >= 2 && !recovered ? "Breached" : "Within target"} />
          <MetricCard label="ERROR RATE" source="5XX" value={metrics.errors} hot={stage >= 3 && !recovered} critical={stage >= 3 && !recovered} recovered={recovered} footerLeft="Budget burn" footerRight={stage >= 3 && !recovered ? "24.2×" : "0.8×"} />
          <article className={`metric-card ${stage >= 2 && !recovered ? "metric-alert" : ""}`}>
            <div className="metric-label">DB POOL <span className="metric-source">POSTGRES</span></div>
            <div className="metric-value">{metrics.pool}</div>
            <div className="capacity-track" aria-label={`Database pool ${metrics.pool}`}><span style={{ width: metrics.pool }} /></div>
            <div className="metric-footer"><span>100 max</span><span>{stage >= 2 && !recovered ? "1,842 pending" : "12 pending"}</span></div>
          </article>
        </div>

        <div className="operations-grid">
          <section className="panel topology-panel">
            <div className="panel-heading"><div><span className="panel-kicker">SERVICE MAP</span><h3>Request topology</h3></div><span className="live-sample">● LIVE · 15s</span></div>
            <div className="topology">
              <div className="topology-flow">
                <TopologyNode icon="U" title="Users" detail={stage === 0 ? "14.2k active" : "1.0m queued"} status="healthy" />
                <FlowArrow label={metrics.rps} />
                <TopologyNode icon="LB" title="Edge LB" detail="4 replicas" status="healthy" />
                <FlowArrow label={stage >= 3 && !recovered ? "retry ×3" : "HTTP"} hot={stage >= 3 && !recovered} />
                <TopologyNode icon="API" title="Ticket API" detail={recovered ? "12 replicas" : "4 replicas"} status={stage >= 2 && !recovered ? "warning" : "healthy"} />
                <FlowArrow label="SQL" hot={stage >= 2 && !recovered} />
                <TopologyNode icon="DB" title="Postgres" detail={stage >= 2 && !recovered ? "pool exhausted" : "primary + 2 RO"} status={stage >= 2 && !recovered ? "critical" : "healthy"} />
              </div>
              <div className="topology-context">
                <div className="context-signal"><span className={`signal-mark ${stage >= 2 && !recovered ? "critical" : ""}`}>!</span><div><small>CURRENT SIGNAL</small><strong>{stages[stage].detail}</strong></div></div>
                <div className="stack-list"><span>kind</span><span>Prometheus</span><span>Loki</span><span>Postgres</span></div>
              </div>
            </div>
          </section>

          <aside className="panel timeline-panel">
            <div className="panel-heading"><div><span className="panel-kicker">SEQUENCE</span><h3>Incident timeline</h3></div></div>
            <div className="timeline-list">
              {visibleTimeline.length === 0 ? <div className="timeline-empty"><span>00</span>Awaiting scenario launch</div> : visibleTimeline.map((item) => (
                <div className="timeline-item" key={item.title}><span className={`timeline-marker ${item.type}`} /><time>{item.time}</time><div><strong>{item.title}</strong><small>{item.type === "critical" ? "Action required" : item.type === "success" ? "System stabilizing" : "Observed"}</small></div></div>
              ))}
            </div>
          </aside>

          <section className="panel terminal-panel">
            <div className="terminal-tabs">
              <button className={activePanel === "terminal" ? "active" : ""} onClick={() => setActivePanel("terminal")}>Virtual terminal</button>
              <button className={activePanel === "runbook" ? "active" : ""} onClick={() => setActivePanel("runbook")}>Investigation guide</button>
              <span>mock shell · scenario-aware</span>
            </div>
            {activePanel === "terminal" ? (
              <>
                <div className="terminal" ref={terminalRef} aria-live="polite">
                  {history.map((item, index) => <div className="terminal-entry" key={`${item.command}-${index}`}><div className="terminal-command"><span>engineer@infragym</span>:<b>~</b>$ {item.command}</div><pre>{item.output}</pre></div>)}
                </div>
                <form className="terminal-input" onSubmit={submitCommand}><span>engineer@infragym:~$</span><input aria-label="Virtual terminal command" value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Type a command or select one below" autoComplete="off" /><button type="submit">Run ↵</button></form>
                <div className="command-chips">{quickCommands.map((item) => <button key={item} onClick={() => runCommand(item)}>{item}</button>)}</div>
              </>
            ) : (
              <div className="runbook">
                <div><span>01</span><strong>Establish impact</strong><p>Confirm which SLI is burning and when the deviation began.</p></div>
                <div><span>02</span><strong>Correlate signals</strong><p>Connect workload events, application errors, and resource pressure.</p></div>
                <div><span>03</span><strong>Mitigate safely</strong><p>Reduce amplification before adding capacity. Watch for recovery.</p></div>
              </div>
            )}
          </section>

          <aside className="panel coach-panel">
            <div className="score-ring" style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}><div><strong>{score}</strong><span>/ 100</span></div></div>
            <div className="coach-title"><span>INCIDENT SCORE</span><h3>{recovered ? "Recovery verified" : "Build your evidence"}</h3></div>
            <div className="checklist">{evidenceItems.map((item) => {
              const complete = evidence.has(item.key);
              return <div className={complete ? "check-item complete" : "check-item"} key={item.key}><span>{complete ? "✓" : "·"}</span><div><strong>{item.label}</strong><small>{complete ? "Evidence captured" : item.hint}</small></div></div>;
            })}</div>
            <button className="mitigate-button" disabled={evidence.size < 3 || stage < 2 || recovered} onClick={applyMitigation}>{recovered ? "Mitigation complete" : evidence.size < 3 ? `Collect ${3 - evidence.size} more signals` : "Apply safe mitigation"}</button>
            <p className="coach-note">Commands run against a scenario model—never against your Mac or a real cluster.</p>
          </aside>
        </div>
      </section>

      <section className="next-labs">
        <div><span className="section-kicker">MVP LEARNING PATH</span><h2>One operational muscle at a time.</h2></div>
        <div className="lab-cards">
          <LabCard number="01" phase="AVAILABLE NOW" title="Ticketing traffic spike" tags="SRE · Kubernetes · Database" current />
          <LabCard number="02" phase="PHASE 02" title="Linux disk full" tags="Linux · Systemd · Recovery" />
          <LabCard number="03" phase="PHASE 03" title="GPU XID 79" tags="NVIDIA · NCCL · GPU cluster" />
        </div>
      </section>

      <footer><div className="brand footer-brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>InfraGym</span></div><p>Built for anyone becoming a world-class Systems Engineer or SRE.</p><span className="mono">OPEN-SOURCE TRAINING PLATFORM · 2026</span></footer>
    </main>
  );
}

function MetricCard({ label, source, value, unit, hot, critical, recovered, footerLeft, footerRight }: { label: string; source: string; value: string; unit?: string; hot?: boolean; critical?: boolean; recovered?: boolean; footerLeft: string; footerRight: string }) {
  return (
    <article className={`metric-card ${hot ? critical ? "metric-critical" : "metric-alert" : ""}`}>
      <div className="metric-label">{label} <span className="metric-source">{source}</span></div>
      <div className="metric-value">{value} {unit && <span>{unit}</span>}</div>
      <Sparkline hot={hot} recovering={recovered} />
      <div className="metric-footer"><span className={hot ? critical ? "trend critical" : "trend hot" : "trend"}>{footerLeft}</span><span>{footerRight}</span></div>
    </article>
  );
}

function TopologyNode({ icon, title, detail, status }: { icon: string; title: string; detail: string; status: string }) {
  return <div className={`topology-node ${status}`}><span className="node-icon">{icon}</span><div><strong>{title}</strong><small>{detail}</small></div></div>;
}

function FlowArrow({ label, hot = false }: { label: string; hot?: boolean }) {
  return <span className={`flow-arrow ${hot ? "hot" : ""}`}><i /><b>{label}</b></span>;
}

function LabCard({ number, phase, title, tags, current = false }: { number: string; phase: string; title: string; tags: string; current?: boolean }) {
  return <article className={`lab-card ${current ? "current" : ""}`}><span className="lab-number">{number}</span><div><span>{phase}</span><h3>{title}</h3><p>{tags}</p></div><strong>→</strong></article>;
}
