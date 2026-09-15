import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { YahooPageResult, YahooPullResponse } from "../api";
import { ImportPull } from "./ImportPull";

// The import pull (issue #55) runs for real against a mocked `fetch`; only the
// refresh nudge is stubbed.
vi.mock("../refreshBus", () => ({ requestRefresh: vi.fn() }));
import { requestRefresh } from "../refreshBus";

const mockRefresh = vi.mocked(requestRefresh);

function fakeResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function page(
  name: string,
  status: YahooPageResult["status"] = "ok",
  error: string | null = null,
): YahooPageResult {
  return { page: name, status, error };
}

function pull(over: Partial<YahooPullResponse> = {}): YahooPullResponse {
  return {
    pull_id: "20260915T120000Z",
    ok: true,
    pages: [page("matchup"), page("players"), page("injuries"), page("standings")],
    waiver_priority_needs_manual_entry: false,
    ...over,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockRefresh.mockReset();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function openAndPaste(text: string) {
  render(<ImportPull />);
  fireEvent.click(screen.getByTestId("import-pull-button"));
  fireEvent.change(screen.getByTestId("import-pull-paste"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("import-pull-submit"));
}

describe("ImportPull", () => {
  it("imports pasted pages, reports success and refreshes the screens", async () => {
    fetchMock.mockResolvedValue(fakeResponse(pull()));
    const pasted = {
      matchup: { week: 3 },
      players: { rows: [] },
      injuries: { rows: [] },
      standings: { rows: [] },
    };

    openAndPaste(JSON.stringify(pasted));

    expect(await screen.findByTestId("pull-yahoo-status")).toHaveTextContent(
      "Pulled all 4 pages",
    );
    expect(mockRefresh).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/yahoo\/import$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(pasted);
  });

  it("shows a per-page failure with the normalizer's error", async () => {
    fetchMock.mockResolvedValue(
      fakeResponse(
        pull({
          ok: false,
          pages: [
            page("matchup"),
            page(
              "standings",
              "failed",
              "YahooNormalizationError: standings payload missing 'rows'",
            ),
          ],
        }),
      ),
    );

    openAndPaste('{"matchup": {}, "standings": {"not_rows": []}}');

    expect(await screen.findByTestId("pull-yahoo-status")).toHaveTextContent(
      "Pulled 1 of 2",
    );
    expect(
      screen.getByTestId("pull-yahoo-page-error-standings"),
    ).toHaveTextContent("standings payload missing 'rows'");
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it("rejects text that is not a JSON object without calling the server", async () => {
    openAndPaste("{not json");

    expect(await screen.findByTestId("import-pull-error")).toHaveTextContent(
      "not valid JSON",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces a rejected request as an error", async () => {
    fetchMock.mockResolvedValue(fakeResponse({ detail: "bad" }, 422));

    openAndPaste('{"roster": {}}');

    expect(await screen.findByTestId("import-pull-error")).toHaveTextContent(
      "422",
    );
    expect(mockRefresh).not.toHaveBeenCalled();
  });
});
