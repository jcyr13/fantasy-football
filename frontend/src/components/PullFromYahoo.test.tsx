import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { YahooPageResult, YahooPullResponse } from "../api";
import { PullFromYahoo } from "./PullFromYahoo";

// `requestRefresh` is the only collaborator worth stubbing; the pull itself and
// the expired-session detection run for real against a mocked `fetch`.
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
    pull_id: "20260830T120000Z",
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

describe("PullFromYahoo", () => {
  it("shows an in-progress state while the pull runs", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));

    render(<PullFromYahoo />);
    const button = screen.getByTestId("pull-yahoo-button");
    fireEvent.click(button);

    await waitFor(() =>
      expect(button).toHaveTextContent("Pulling from Yahoo…"),
    );
    expect(button).toBeDisabled();

    resolve(fakeResponse(pull()));
    await screen.findByTestId("pull-yahoo-status");
  });

  it("reports a whole-roster success and refreshes the screens", async () => {
    fetchMock.mockResolvedValue(fakeResponse(pull()));

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    expect(await screen.findByTestId("pull-yahoo-status")).toHaveTextContent(
      "Pulled all 4 pages",
    );
    expect(mockRefresh).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("pull-yahoo-button")).toBeEnabled();
  });

  it("surfaces the waiver-priority manual-entry reminder when the pull reports it", async () => {
    fetchMock.mockResolvedValue(
      fakeResponse(pull({ waiver_priority_needs_manual_entry: true })),
    );

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    expect(
      await screen.findByTestId("pull-yahoo-waiver-reminder"),
    ).toHaveTextContent("waiver priority needs manual entry");
  });

  it("shows which pages failed on a partial pull, and still refreshes", async () => {
    fetchMock.mockResolvedValue(
      fakeResponse(
        pull({
          ok: false,
          pages: [
            page("matchup"),
            page("players"),
            page("injuries"),
            page("standings", "failed", "TimeoutError: page never settled"),
          ],
        }),
      ),
    );

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    expect(await screen.findByTestId("pull-yahoo-status")).toHaveTextContent(
      "Pulled 3 of 4 — standings failed",
    );
    expect(
      screen.getByTestId("pull-yahoo-page-error-standings"),
    ).toHaveTextContent("standings: TimeoutError: page never settled");
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it("treats a lone sign-in-phrase page failure as a partial pull, not a session expiry", async () => {
    fetchMock.mockResolvedValue(
      fakeResponse(
        pull({
          ok: false,
          pages: [
            page("matchup"),
            page("players"),
            page("injuries"),
            page("standings", "failed", "HTTPError: 401 Yahoo sign-in required"),
          ],
        }),
      ),
    );

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    expect(await screen.findByTestId("pull-yahoo-status")).toHaveTextContent(
      "Pulled 3 of 4 — standings failed",
    );
    expect(screen.queryByTestId("pull-yahoo-expired")).toBeNull();
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it("prompts a re-sign-in on an expired session, then retries successfully", async () => {
    const expired = pull({
      ok: false,
      pages: [
        page("matchup", "failed", "HTTPError: 401 Yahoo sign-in required"),
        page("players", "failed", "HTTPError: 401 Yahoo sign-in required"),
        page("injuries", "failed", "HTTPError: 401 Yahoo sign-in required"),
        page("standings", "failed", "HTTPError: 401 Yahoo sign-in required"),
      ],
    });
    fetchMock.mockResolvedValueOnce(fakeResponse(expired));

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    expect(await screen.findByTestId("pull-yahoo-expired")).toHaveTextContent(
      "sign in again in the Yahoo window",
    );
    expect(mockRefresh).not.toHaveBeenCalled();
    const button = screen.getByTestId("pull-yahoo-button");
    expect(button).toHaveTextContent("Retry pull");
    expect(button).toBeEnabled();

    // Signed back in; the retry lands.
    fetchMock.mockResolvedValueOnce(fakeResponse(pull()));
    fireEvent.click(button);

    expect(await screen.findByTestId("pull-yahoo-status")).toHaveTextContent(
      "Pulled all 4 pages",
    );
    expect(screen.queryByTestId("pull-yahoo-expired")).toBeNull();
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it("degrades to a short notice when the backend has no source wired (503)", async () => {
    fetchMock.mockResolvedValue(fakeResponse({ detail: "no source" }, 503));

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    expect(
      await screen.findByTestId("pull-yahoo-unavailable"),
    ).toHaveTextContent("Assisted pull needs the desktop app.");
    expect(screen.getByTestId("pull-yahoo-button")).toBeDisabled();
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it("shows a retryable error on any other failure", async () => {
    fetchMock.mockResolvedValue(fakeResponse({ detail: "boom" }, 500));

    render(<PullFromYahoo />);
    fireEvent.click(screen.getByTestId("pull-yahoo-button"));

    await waitFor(() =>
      expect(screen.getByText(/Pull failed —/)).toBeInTheDocument(),
    );
    expect(screen.getByTestId("pull-yahoo-button")).toHaveTextContent(
      "Retry pull",
    );
  });
});
