# PRD — Florida Scratch-Off EV Tool

## 1. Problem

Florida Lottery scratch-off games publish overall odds on the back of each ticket, but those odds describe the game at print time. Once tickets start selling and prizes get claimed, the real expected value drifts. A game whose top prizes are already gone is worse than advertised; a fresh game with its full prize pool is at peak EV.

The Florida Lottery does publish remaining-prize counts per game, but only on per-game pages, with no ranking, no EV calculation, and no way to see what changed since last week.

## 2. Goal

A small, ad-hoc CLI that:

1. Scrapes current remaining-prize data for every active Florida scratch-off.
2. Computes expected value per ticket.
3. Ranks games so the user can see which are currently worth the money.
4. Tracks runs over time so new games and ended games are easy to spot.

## 3. Users

Solo user (the repo owner). No multi-user, auth, or hosting concerns.

## 4. Non-Goals (v1)

- No scheduling, cron, web UI, or dashboard.
- No historical trend charts (history is stored, but visualization is v2).
- No tax-adjusted EV, annuity vs lump-sum modeling for top prizes.
- No second-chance drawing valuation.
- No multi-state lotteries.
- No alerting when a game crosses a threshold.
- No proxy rotation or CAPTCHA handling.

## 5. Data Source

Two clean JSON endpoints — no scraping, no headless browser needed.

- **Game list (all active scratch-offs):**
  `GET https://floridalottery.com/content/flalottery-web/us/en/games/scratch-offs/view.scratch-offs.json`
  No special headers required. Returns `{data: [{id, name, price, topPrize, isFeatured, teaserImage}, ...]}`.

- **Per-game detail (prize tiers + remaining counts):**
  `GET https://apim-website-prod-eastus.azure-api.net/scratchgamesapp/getscratchinfo?id={game_id}`
  Requires header `x-partner: web` (otherwise 401). No auth key. Returns:

  ```json
  {
    "Id": "7028", "GameName": "...", "TicketPrice": 20,
    "LaunchDate": "...", "EndDate": "...", "RedemptionDate": "...",
    "OverallOdds": 2.79,
    "OddsTiers": [
      {"PrizeAmount": "$5,000,000.00", "WinningOdds": "1-in-3000000",
       "TotalPrizes": 4, "PrizesRemaining": 2, "PrizesPaid": 2},
      ...
    ],
    "Tpr": [...]
  }
  ```

- **No bulk-detail endpoint discovered** — must call `getscratchinfo` once per game (~80 calls per run). Polite throttling still applies.

## 6. Core Calculation

For each game:

```text
est_tickets_at_tier = total_printed_at_tier × odds_1_in_at_tier
est_total_tickets   = median(est_tickets_at_tier across tiers)
fraction_sold       = 1 − (Σ remaining / Σ total_printed)
est_remaining       = est_total_tickets × (1 − fraction_sold)

EV_per_ticket  = Σ (prize_amount × remaining) / est_remaining
EV_minus_price = EV_per_ticket − ticket_price
```

Compute a second estimator using overall odds (`total_remaining / overall_odds`) and emit a sanity flag if the two estimators diverge by more than 15%. Don't pick one silently.

## 7. Tech Stack

- Python 3.11+
- `requests` — JSON API calls (no headless browser needed)
- SQLite via stdlib `sqlite3` — run history
- `rich` — CLI table output
- `argparse` (stdlib) — CLI

Setup: `pip install -e .`. No Playwright, no browser install.

## 8. Project Layout

```text
florida-scratcher-odds/
  README.md
  PRD.md
  pyproject.toml
  .gitignore
  src/fl_scratchers/
    __init__.py
    scrape.py        # requests.get() against the two JSON endpoints
    parse.py         # response dict → normalized model (testable, no network)
    ev.py            # EV math
    storage.py       # SQLite read/write
    cli.py           # entry point
  tests/
    fixtures/        # saved real-page HTML
    test_parse.py
    test_ev.py
  data/
    scratchers.db    # gitignored
```

Network code (`scrape.py`) and parsing (`parse.py`) are deliberately separate so the parser can be tested against saved fixtures without hitting the network.

## 9. Storage Schema

```sql
CREATE TABLE runs (
  run_id      INTEGER PRIMARY KEY,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  games_seen  INTEGER
);

CREATE TABLE game_snapshots (
  run_id                 INTEGER REFERENCES runs(run_id),
  game_id                INTEGER,
  name                   TEXT,
  ticket_price           REAL,
  overall_odds           REAL,
  launch_date            TEXT,
  end_date               TEXT,
  status                 TEXT,    -- active | ending | ended
  tiers_json             TEXT,    -- JSON array of {prize, total_printed, remaining, odds_1_in}
  ev_per_ticket          REAL,
  ev_minus_price         REAL,
  est_tickets_remaining  REAL,
  sanity_flag            TEXT,    -- null if both estimators agree
  PRIMARY KEY (run_id, game_id)
);

CREATE INDEX idx_snapshots_game ON game_snapshots(game_id);
```

New-game detection: `game_id` present in latest run but not previous run.
Ended-game detection: `game_id` present in previous run but not latest run.

## 10. CLI

```bash
fl-scratchers scrape                  # full scrape, write new run row
fl-scratchers rank [--top N] [--min-price P]   # ranked latest run
fl-scratchers diff                    # new / removed games since last run
fl-scratchers show <game_id>          # tier breakdown + EV for one game
fl-scratchers export --csv out.csv    # latest run to CSV
```

`rank` output columns: game_id, name, price, EV, EV−price, est_tickets_remaining, top_prize_remaining, sanity_flag.

## 11. Edge Cases

- **Top prize exhausted:** keep the game, mark `top_prize_exhausted=True`, surface in output.
- **Ended game:** detail page may 404 or show an "ended" banner — catch, write `status="ended"`, skip EV.
- **Single-game parse failure:** log, write row with null tiers, continue. One bad game must not abort the run.
- **Estimator divergence > 15%:** populate `sanity_flag`, do not silently pick one.
- **Brand-new game:** `fraction_sold` near 0; EV ≈ printed-odds EV. Label as new.
- **HTML structure change:** parser tests run against fixtures in `tests/fixtures/`, so structural drift breaks tests instead of producing silent garbage.
- **Playwright timeout:** retry once with longer wait, then mark game fetch-failed for that run.
- **Money precision:** use `Decimal` inside parse, cast to float only at the SQLite/output boundary.

## 12. Politeness / Anti-Abuse

- Sequential fetches, single browser context reused.
- 1.5–2s jitter between detail page fetches.
- Realistic User-Agent.
- ~80 active games × 2s ≈ under 5 minutes per full run.

## 13. Build Order

1. Skeleton: `pyproject.toml`, package layout, Playwright install.
2. `scrape.list_games` against `/view` (cheapest path, validates approach).
3. Save one rendered detail page to `tests/fixtures/`; build `parse.parse_detail` test-first.
4. Wire `scrape.fetch_detail` (Playwright) once parser passes.
5. SQLite layer + `runs` writes.
6. `ev.py` with both estimators + sanity flag.
7. CLI commands in order: `scrape`, `rank`, `diff`, `show`, `export`.

## 14. Ranking Behavior

- Do **not** filter games with zero remaining top prizes — they stay in the ranked list.
- Sort by EV per ticket (computed from remaining prizes across all tiers, including the small ones), so games whose top prizes are gone naturally fall in the ranking by virtue of their lower EV.
- Surface a `top_prize_exhausted` flag in output for visibility, but it does not affect inclusion or sort order.

## 15. Open Questions

- Is there a hidden JSON endpoint behind the JS-rendered pages that would let us skip Playwright? Worth one focused dig before committing to the headless browser path. (Tracked in [TODO.md](TODO.md).)
