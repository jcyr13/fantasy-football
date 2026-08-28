export interface HealthResponse {
  status: "ok" | "degraded";
  sqlite: "ok" | "error";
  duckdb: "ok" | "error";
  scheduler: "running" | "stopped";
  time: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  if (!res.ok) {
    throw new Error(`health check failed: ${res.status}`);
  }
  return (await res.json()) as HealthResponse;
}
