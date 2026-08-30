import { useEffect, useRef, useState } from "react";

import { onRefresh } from "./refreshBus";

export type Loadable<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T; refreshing: boolean }
  | { kind: "error"; message: string };

/**
 * Call `fn` on mount, and — when `intervalMs > 0` — every `intervalMs`
 * thereafter, tracking the latest outcome as a `Loadable`. `intervalMs <= 0`
 * fetches once and does not poll.
 *
 * `key` re-arms the fetch when it changes (e.g. the This Week engine toggle).
 * A re-arm keeps the last `ready` data on screen with `refreshing: true` rather
 * than flashing back to `loading`, so a toggle swaps content in place.
 *
 * `fn` is read fresh each tick via a ref and is not a dependency, so an inline
 * arrow is fine.
 *
 * Every live hook also refetches on `requestRefresh()` (see `refreshBus`), which
 * the "Pull from Yahoo" control fires after a pull lands new server-side data.
 */
export function usePoll<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  key: string | number = "",
): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ kind: "loading" });
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;
    setState((prev) =>
      prev.kind === "ready" ? { ...prev, refreshing: true } : { kind: "loading" },
    );
    const tick = () => {
      fnRef
        .current()
        .then((data) => {
          if (!cancelled) setState({ kind: "ready", data, refreshing: false });
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            const message = err instanceof Error ? err.message : String(err);
            setState({ kind: "error", message });
          }
        });
    };
    tick();
    const unsubscribe = onRefresh(tick);
    if (intervalMs <= 0) {
      return () => {
        cancelled = true;
        unsubscribe();
      };
    }
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      unsubscribe();
      clearInterval(id);
    };
  }, [intervalMs, key]);

  return state;
}
