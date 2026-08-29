import type { NewsItem } from "../api";
import { fetchNews } from "../api";
import { humanizeLabel } from "../format";
import { usePoll } from "../usePoll";

// The top-pinned 48-hour news strip. Scrolls with CSS; pauses on hover (see
// `.ticker:hover .ticker-track` in styles.css). Each item opens its source in a
// new tab. Hides itself behind a small notice when every source failed in the
// latest poll, when the window is empty, or when the endpoint is unreachable.

function Sequence({ items, clone }: { items: NewsItem[]; clone?: boolean }) {
  return (
    <div className="ticker-seq" aria-hidden={clone || undefined}>
      {items.map((item, i) => {
        const bucket = item.buckets[0] ?? "news";
        return (
          <a
            key={`${item.url}-${i}`}
            className="ticker-item"
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span className={`bucket bucket--${bucket}`}>
              {humanizeLabel(bucket)}
            </span>
            {item.title}
            <span className="ticker-src">{item.source}</span>
          </a>
        );
      })}
    </div>
  );
}

export function NewsTicker() {
  const state = usePoll(fetchNews, 120_000);

  if (state.kind === "error") {
    return (
      <div className="ticker ticker--down" role="status">
        News ticker unavailable — feed unreachable.
      </div>
    );
  }
  if (state.kind === "loading") {
    return <div className="ticker ticker--loading" aria-hidden="true" />;
  }

  const feed = state.data;
  if (feed.all_sources_failed) {
    return (
      <div className="ticker ticker--down" role="status">
        News ticker unavailable — all sources failed.
      </div>
    );
  }
  if (feed.items.length === 0) {
    return (
      <div className="ticker ticker--down" role="status">
        No tagged NFL news in the last {feed.window_hours}h.
      </div>
    );
  }

  // Two identical sequences; the keyframe scrolls the track by exactly one
  // sequence width (-50%), so the second lands where the first began — no seam.
  return (
    <div className="ticker" aria-label="NFL news ticker" role="region">
      <div className="ticker-track">
        <Sequence items={feed.items} />
        <Sequence items={feed.items} clone />
      </div>
    </div>
  );
}
