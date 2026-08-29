import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AutoFill, LineupLabResult, LineupSlotProjection } from "../api";
import { LineupLab } from "./LineupLab";

vi.mock("../api", () => ({
  fetchAutoFill: vi.fn(),
  computeLineupLab: vi.fn(),
}));

// Imported after the mock so these are the vi.fn() stubs.
import { computeLineupLab, fetchAutoFill } from "../api";

const mockAutoFill = vi.mocked(fetchAutoFill);
const mockCompute = vi.mocked(computeLineupLab);

function slot(
  id: string,
  position: string,
  mean: number,
): LineupSlotProjection {
  return {
    player_id: id,
    name: id.toUpperCase(),
    position,
    slot: "",
    mean,
    floor: mean - 5,
    ceiling: mean + 5,
    low_confidence: false,
    reasons: [],
    resolved: true,
  };
}

// A legal-10 plus two bench players. The W/R/T flex is filled by a WR here.
const ROSTER: LineupSlotProjection[] = [
  slot("qb1", "QB", 20),
  slot("rb1", "RB", 14),
  slot("rb2", "RB", 12),
  slot("wr1", "WR", 13),
  slot("wr2", "WR", 11),
  slot("te1", "TE", 9),
  slot("flexwr", "WR", 10),
  slot("k1", "K", 8),
  slot("def1", "DEF", 7),
  slot("idp1", "IDP", 6),
  slot("rb3", "RB", 15),
  slot("wr3", "WR", 4),
];

const MAX_P_WIN = [
  "qb1",
  "rb1",
  "rb2",
  "wr1",
  "wr2",
  "te1",
  "flexwr",
  "k1",
  "def1",
  "idp1",
];

const AUTO_FILL: AutoFill = {
  floor: MAX_P_WIN,
  ceiling: [...MAX_P_WIN.slice(0, 9), "rb3"],
  max_p_win: MAX_P_WIN,
  max_ev: MAX_P_WIN,
  roster: ROSTER,
  caveats: ["projection baseline is a trailing mean (v1)"],
};

// A stand-in for the backend's Lineup Lab compute: always returns numbers, and
// marks the lineup illegal when the starter count is not 10 or when a starter
// is also on IR (mirroring backend `api/weekly.py` / `serialize.py`).
function fakeCompute(
  starters: string[],
  ir: string[] = [],
): Promise<LineupLabResult> {
  const overlap = starters.find((s) => ir.includes(s));
  if (overlap) {
    return Promise.resolve({
      starter_ids: starters,
      legal: false,
      reason: `${overlap} is a starter and also on IR`,
      total: 100,
      floor: 80,
      ceiling: 125,
      win_probability: 0.4,
      caveats: [],
    });
  }
  if (starters.length !== 10) {
    return Promise.resolve({
      starter_ids: starters,
      legal: false,
      reason: `a legal lineup starts 10 players, got ${starters.length}`,
      total: 90,
      floor: 70,
      ceiling: 120,
      win_probability: 0.33,
      caveats: [],
    });
  }
  const total = starters.includes("rb3") ? 118 : 110;
  return Promise.resolve({
    starter_ids: starters,
    legal: true,
    reason: null,
    total,
    floor: total - 20,
    ceiling: total + 25,
    win_probability: starters.includes("rb3") ? 0.61 : 0.52,
    caveats: ["projection baseline is a trailing mean (v1)"],
  });
}

function drag(fromTestId: string, toTestId: string) {
  fireEvent.dragStart(screen.getByTestId(fromTestId));
  const target = screen.getByTestId(toTestId);
  fireEvent.dragOver(target);
  fireEvent.drop(target);
}

beforeEach(() => {
  mockAutoFill.mockReset();
  mockCompute.mockReset();
  mockAutoFill.mockResolvedValue(AUTO_FILL);
  mockCompute.mockImplementation(fakeCompute);
});

describe("Lineup Lab interaction", () => {
  it("scores the auto-filled lineup on load", async () => {
    render(<LineupLab />);

    await screen.findByTestId("player-qb1");
    await waitFor(() =>
      expect(screen.getByTestId("lab-total")).toHaveTextContent("110.0"),
    );
    expect(mockCompute).toHaveBeenCalledWith(MAX_P_WIN, []);
    expect(screen.getByTestId("lab-winprob")).toHaveTextContent("52%");
    expect(screen.queryByTestId("illegal-banner")).toBeNull();
  });

  it("recomputes after a drag between Start and Bench", async () => {
    render(<LineupLab />);
    await screen.findByTestId("player-rb3");
    await waitFor(() =>
      expect(screen.getByTestId("lab-total")).toHaveTextContent("110.0"),
    );

    // Bench rb1, start rb3 — still ten, but a different ten.
    drag("player-rb1", "zone-bench");
    drag("player-rb3", "zone-start");

    await waitFor(() =>
      expect(screen.getByTestId("lab-total")).toHaveTextContent("118.0"),
    );
    expect(screen.getByTestId("lab-winprob")).toHaveTextContent("61%");
    const lastCall = mockCompute.mock.calls.at(-1);
    expect(lastCall?.[0]).toContain("rb3");
    expect(lastCall?.[0]).not.toContain("rb1");
    expect(lastCall?.[0]).toHaveLength(10);
    expect(screen.queryByTestId("illegal-banner")).toBeNull();
  });

  it("marks an illegal lineup when a drag leaves the wrong starter count", async () => {
    render(<LineupLab />);
    await screen.findByTestId("player-idp1");
    await waitFor(() =>
      expect(screen.getByTestId("lab-total")).toHaveTextContent("110.0"),
    );

    // Move the only IDP to IR — now nine starters.
    drag("player-idp1", "zone-ir");

    const banner = await screen.findByTestId("illegal-banner");
    expect(banner).toHaveTextContent("got 9");
    expect(screen.getByTestId("lab-total")).toHaveTextContent("90.0");

    // The D slot's player is back — legal again, banner gone.
    drag("player-idp1", "zone-start");
    await waitFor(() =>
      expect(screen.queryByTestId("illegal-banner")).toBeNull(),
    );
    expect(mockCompute).toHaveBeenLastCalledWith(
      expect.arrayContaining(["idp1"]),
      [],
    );
  });
});
