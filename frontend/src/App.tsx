import { useState } from "react";
import type { ComponentType } from "react";

import { FreshnessHeader } from "./components/FreshnessHeader";
import { Logo } from "./components/Logo";
import { NewsTicker } from "./components/NewsTicker";
import { History } from "./screens/History";
import { LineupLab } from "./screens/LineupLab";
import { TeamOutlook } from "./screens/TeamOutlook";
import { ThisWeek } from "./screens/ThisWeek";
import { TradeDesk } from "./screens/TradeDesk";
import { WaiverFA } from "./screens/WaiverFA";

// The shell: the top-pinned news ticker and the always-visible data-freshness
// header wrap every screen. This Week and Lineup Lab shipped in issue #18; the
// four remaining screens — Waiver/FA, Team Outlook, Trade Desk, History — are
// issue #19. All six are presentational over the ticket #15/#16 endpoints.

type Tab =
  | "this-week"
  | "lineup-lab"
  | "waiver-fa"
  | "team-outlook"
  | "trade-desk"
  | "history";

const TABS: { id: Tab; label: string }[] = [
  { id: "this-week", label: "This Week" },
  { id: "lineup-lab", label: "Lineup Lab" },
  { id: "waiver-fa", label: "Waiver / FA" },
  { id: "team-outlook", label: "Team Outlook" },
  { id: "trade-desk", label: "Trade Desk" },
  { id: "history", label: "History" },
];

const SCREENS: Record<Tab, ComponentType> = {
  "this-week": ThisWeek,
  "lineup-lab": LineupLab,
  "waiver-fa": WaiverFA,
  "team-outlook": TeamOutlook,
  "trade-desk": TradeDesk,
  history: History,
};

export function App() {
  const [tab, setTab] = useState<Tab>("this-week");
  const Screen = SCREENS[tab];

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
        <Screen />
      </main>
    </>
  );
}
