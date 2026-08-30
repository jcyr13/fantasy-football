# Running the Dead Parrots Dashboard — a step-by-step guide for beginners

This guide is for one person: the owner, running the dashboard on their own
Windows computer. There is **no server** anymore. The app is a normal desktop
program — you install it, open it, and it runs the whole dashboard on your
machine.

If you are looking for the old "deploy to a VPS over Tailscale" guide: that
approach is **retired** (`../docs/adr/0016`). Its runbook is kept as the
"old VPS deployment" appendix in [`README.md`](README.md), and the full beginner
version is in this file's git history.

---

## Table of contents

1. [The big picture](#1-the-big-picture)
2. [Words you will see](#2-words-you-will-see)
3. [Installing the app](#3-installing-the-app)
4. [First run — signing into Yahoo](#4-first-run--signing-into-yahoo)
5. [Pulling your data](#5-pulling-your-data)
6. [What updates on its own](#6-what-updates-on-its-own)
7. [If you close the app for a while](#7-if-you-close-the-app-for-a-while)
8. [Updating to a new version](#8-updating-to-a-new-version)
9. [When something goes wrong](#9-when-something-goes-wrong)
10. [For developers: run it without the installer](#10-for-developers-run-it-without-the-installer)

---

## 1. The big picture

The dashboard has two halves that used to run on a rented server and now both
run inside one desktop app:

- **the brain** — a small program (the "backend") that does all the maths:
  scoring, projections, the win-probability simulation, the trade and waiver
  reads.
- **the screens** — the web pages you actually look at.

The desktop app starts the brain quietly in the background, shows you the
screens, and keeps all your data in a folder that belongs to your Windows user
account. Nothing is on the internet. Nothing is reachable from your phone. That
is the trade you accepted when you chose the desktop app.

To get your team's data out of Yahoo, the app has a **built-in browser window**.
You sign into Yahoo there once, and from then on a **Pull from Yahoo** button
copies the four pages it needs (your matchup, the player list, the injury
report, the standings) in one click.

---

## 2. Words you will see

| Word | Plain English |
| --- | --- |
| **Backend / the brain** | the background program that does the calculations |
| **Assisted pull** | the one-click copy of your four Yahoo pages into the app |
| **Freshness header** | the strip at the top of the dashboard saying how old each data source is |
| **Snapshot** | a frozen copy of one week's numbers, kept so the History screen never loses a week |
| **Catch-up** | when you open the app, it re-runs any scheduled update it missed while closed |
| **nflverse** | the free NFL stats feed the projections are built on |
| **Consensus feed** | other people's weekly projections, used as a cross-check |

---

## 3. Installing the app

> The packaged installer is being built in a follow-up task. When it is ready,
> this section becomes: download `DeadParrotsDashboard-Setup-x.y.z.exe`, run it,
> and click through the one-time Windows SmartScreen warning ("More info" →
> "Run anyway" — the app is not code-signed yet, so Windows does not recognise
> the publisher). Until then, use
> [section 10](#10-for-developers-run-it-without-the-installer).

Once installed, launch **Dead Parrots Dashboard** from the Start menu. The first
launch takes a few seconds longer while it sets up its data folder.

---

## 4. First run — signing into Yahoo

1. In the app, open the **Yahoo** window (a button near the freshness header).
2. A real browser page loads. Sign into your Yahoo account the normal way,
   including any two-factor step.
3. Close the Yahoo window. You will **not** have to do this again — the app
   remembers the session between launches. You only sign in again if Yahoo logs
   you out, and the app will prompt you when that happens.

---

## 5. Pulling your data

1. Click **Pull from Yahoo**.
2. The app loads your four Yahoo pages in the background browser and reads each
   one. You get a per-page result: four green ticks, or a tick per page that
   worked and a note on any that did not.
3. The Yahoo-fed screens fill in: **This Week** (your opponent and their likely
   lineup), **Waiver / FA**, **Trade Desk**, and the standings.
4. If Yahoo does not show a waiver-priority number on the standings page, the
   app flags it and asks you to type it in by hand — this is expected some
   weeks, not a bug.

The **freshness header** now shows a real time for "Yahoo" instead of "never".

The other two data sources — **nflverse** and the **consensus feed** — fill in
by themselves (see the next section). If they still say "never" a minute after
you first open the app, give it a few minutes; the catch-up is fetching them.

---

## 6. What updates on its own

While the app is open, it refreshes on a schedule:

| Update | When |
| --- | --- |
| nflverse stats | Tuesday morning |
| Consensus projections | Wednesday morning |
| News ticker | every ~30 minutes |
| Weekly snapshot | Sunday late morning, before the 1pm games |

You do not need to do anything for these. The **Yahoo** pull is the only one
that is always manual — click **Pull from Yahoo** whenever the freshness header
says Yahoo is stale (it will nudge you Wednesday, Saturday, and Sunday
mornings).

---

## 7. If you close the app for a while

The scheduled updates above only happen while the app is **open**. That is fine
— when you next open it, the app runs a **catch-up**: any update whose time
slot passed while you were closed is run right then.

The one that matters most: if you had the app closed all of Sunday, the next
time you open it (once that week's games have finished) it still captures that
week's **snapshot**, so the History screen does not have a hole. You do not have
to remember to do anything.

---

## 8. Updating to a new version

Download the new installer and run it; it replaces the old version in place.
Your data folder is separate from the program, so nothing is lost — your Yahoo
sign-in, your snapshots, and your cached stats all carry over.

---

## 9. When something goes wrong

**The dashboard is blank or every panel shows an error.**
The brain may still be starting. Wait ten seconds and reload. If it persists,
quit the app completely and reopen it.

**"Pull from Yahoo" fails on every page.**
Your Yahoo session probably expired. Open the Yahoo window, sign in again, and
retry the pull.

**"Pull from Yahoo" works but a screen is still empty.**
That screen also needs nflverse data. Check the freshness header — if nflverse
says "never", wait for the catch-up, or (developers) run
`python -m deadparrots.ingest` in the checkout.

**The freshness header says consensus is "never" and it is pre-season.**
Normal. `ffanalytics` has nothing to publish yet; the app falls back to the
Sleeper projections automatically once the season starts.

**Where is my data?**
In your Windows user profile, under the app's data folder (the app shows the
exact path in its About screen). Back that folder up if you care about the
snapshot history.

---

## 10. For developers: run it without the installer

You can run both halves by hand from a source checkout — this is also how the
desktop shell launches them.

```sh
# 1. the brain
cd backend
uv sync
uv run uvicorn deadparrots.app:app --reload      # http://localhost:8000

# 2. the screens (a second terminal)
cd frontend
npm install
npm run dev                                      # http://localhost:5173
```

Open `http://localhost:5173`.

The live Yahoo pull needs the desktop shell's signed-in browser window, which is
a follow-up task. Until then, develop the Yahoo-fed screens against an archived
pull:

```sh
cd backend
uv run python -m deadparrots.yahoo --replay <pull_id>
```

Seed the other feeds so the screens are not empty:

```sh
cd backend
uv run python -m deadparrots.ingest
uv run python -m deadparrots.consensus --week <current-week>
```

The consensus R sidecar is a standalone container — see
[`../rsidecar/README.md`](../rsidecar/README.md).
