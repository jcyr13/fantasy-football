// A process-wide "refetch now" signal. Screens poll independently (most with
// `usePoll(..., 0)` — one fetch, no interval), so an action that changes the
// backing data on the server — the Yahoo assisted pull (issue #46) — has no
// other way to make the already-mounted screens reflect it. Every `usePoll`
// subscribes; `requestRefresh()` re-runs them all.

type Listener = () => void;

const listeners = new Set<Listener>();

/** Subscribe to refresh requests; returns an unsubscribe. */
export function onRefresh(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Ask every live `usePoll` to refetch. */
export function requestRefresh(): void {
  for (const listener of [...listeners]) {
    listener();
  }
}
