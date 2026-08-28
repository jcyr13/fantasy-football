import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "./api";

type State =
  | { kind: "loading" }
  | { kind: "ready"; health: HealthResponse }
  | { kind: "error"; message: string };

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((health) => {
        if (!cancelled) setState({ kind: "ready", health });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err);
          setState({ kind: "error", message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 640 }}>
      <h1>Dead Parrots Dashboard</h1>
      <p>RIP TIDE League decision-support — scaffold.</p>
      <section>
        <h2>Backend health</h2>
        {state.kind === "loading" && <p>Checking…</p>}
        {state.kind === "error" && <p role="alert">Backend unreachable: {state.message}</p>}
        {state.kind === "ready" && (
          <ul>
            <li>status: {state.health.status}</li>
            <li>sqlite: {state.health.sqlite}</li>
            <li>duckdb: {state.health.duckdb}</li>
            <li>scheduler: {state.health.scheduler}</li>
            <li>time: {state.health.time}</li>
          </ul>
        )}
      </section>
    </main>
  );
}
