import { useState } from "react";

import { FreshnessHeader } from "./components/FreshnessHeader";
import { Logo } from "./components/Logo";
import { NewsTicker } from "./components/NewsTicker";
import { LineupLab } from "./screens/LineupLab";
import { ThisWeek } from "./screens/ThisWeek";

// The shell: the top-pinned news ticker and the always-visible data-freshness
// header wrap every screen. This Week and Lineup Lab ship here (issue #18); the
// four remaining screens are issue #19.

type Tab = "this-week" | "lineup-lab";

const TABS: { id: Tab; label: string }[] = [
  { id: "this-week", label: "This Week" },
  { id: "lineup-lab", label: "Lineup Lab" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("this-week");

  return (
    <>
      <NewsTicker />
      <FreshnessHeader />
      <header className="masthead">
        <Logo />
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className="tab"
              aria-current={tab === t.id ? "page" : undefined}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="screen">
        {tab === "this-week" ? <ThisWeek /> : <LineupLab />}
      </main>
    </>
  );
}
