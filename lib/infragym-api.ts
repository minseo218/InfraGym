export type Evidence = "metrics" | "events" | "logs" | "network";

export type SessionState = {
  id: string;
  scenario: string;
  stage: 0 | 1 | 2 | 3 | 4;
  status: "active" | "recovered" | "completed";
  evidence: Evidence[];
  score: number;
  report: IncidentReport | null;
};

export type CommandResult = {
  command: string;
  output: string;
  evidence: Evidence[];
  score: number;
};

export type IncidentReport = {
  score: number;
  breakdown: {
    investigation_and_recovery: number;
    root_cause: number;
    mitigation: number;
    prevention: number;
  };
  mttr_seconds: number;
  summary: string;
};

const configuredUrl = process.env.NEXT_PUBLIC_INFRAGYM_API_URL?.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T | null> {
  if (!configuredUrl) return null;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 1800);
  try {
    const response = await fetch(`${configuredUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`InfraGym API returned ${response.status}`);
    return (await response.json()) as T;
  } catch {
    return null;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function createSession() {
  return request<SessionState>("/api/v1/sessions", { method: "POST" });
}

export function advanceSession(sessionId: string) {
  return request<SessionState>(`/api/v1/sessions/${sessionId}/advance`, { method: "POST" });
}

export function executeRemoteCommand(sessionId: string, command: string) {
  return request<CommandResult>(`/api/v1/sessions/${sessionId}/commands`, {
    method: "POST",
    body: JSON.stringify({ command }),
  });
}

export function mitigateSession(sessionId: string) {
  return request<SessionState & { output: string }>(
    `/api/v1/sessions/${sessionId}/mitigate`,
    { method: "POST" },
  );
}

export function completeSession(
  sessionId: string,
  payload: { root_cause: string; mitigation: string; prevention: string },
) {
  return request<IncidentReport>(`/api/v1/sessions/${sessionId}/complete`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
