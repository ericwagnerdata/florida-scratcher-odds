# TODO

Working build checklist. See [PRD.md](PRD.md) for design rationale.

## Pre-build decisions

- [x] Hunt for a hidden JSON endpoint. **Found two clean JSON APIs — Playwright dropped.**
  - List: `GET https://floridalottery.com/content/flalottery-web/us/en/games/scratch-offs/view.scratch-offs.json` (no headers)
  - Detail: `GET https://apim-website-prod-eastus.azure-api.net/scratchgamesapp/getscratchinfo?id={id}` (header `x-partner: web` required)
- [x] Ranking: don't filter games with zero top prizes remaining — surface them in the ranked list, sorted by remaining-value-based EV.

## Phase 1 — Skeleton

- [ ] `pyproject.toml` with deps: `requests`, `rich`.
- [ ] `.gitignore` (`.venv/`, `data/*.db`, `__pycache__/`).
- [ ] Package layout under `src/fl_scratchers/`.
- [ ] `pip install -e .` works locally.

## Phase 2 — List fetcher

- [ ] `scrape.list_games()` — `GET` the AEM list endpoint, return `[{game_id, name, ticket_price, advertised_top_prize}, ...]`.
- [ ] Handle non-200 cleanly.

## Phase 3 — Detail parser (test-first)

- [ ] Save one APIM JSON response to `tests/fixtures/game_<id>.json`.
- [ ] `parse.parse_detail(json_dict) -> dict` — pure function, no network.
- [ ] Extracted fields: `game_id`, `name`, `ticket_price`, `overall_odds`, `launch_date`, `end_date`, `redemption_date`, `tiers`.
- [ ] Each tier: `{prize_amount (Decimal), total_printed, remaining, odds_1_in}`.
- [ ] Parse `"$5,000.00"` → `Decimal("5000.00")` and `"1-in-76497"` → `76497`.
- [ ] Unit tests against fixture pass.

## Phase 4 — Detail fetcher

- [ ] `scrape.fetch_detail(game_id)` — `requests.get()` with `x-partner: web` header.
- [ ] 1s jitter between calls (~80 games × 1s ≈ <2 min).
- [ ] Realistic User-Agent.
- [ ] Retry once on 5xx/timeout, mark fetch-failed otherwise.

## Phase 5 — Storage

- [ ] `storage.init_db()` creates `runs` and `game_snapshots` tables (schema in PRD §9).
- [ ] `storage.start_run() -> run_id`.
- [ ] `storage.write_snapshot(run_id, game_dict)`.
- [ ] `storage.finish_run(run_id, games_seen)`.

## Phase 6 — EV calculation

- [ ] `ev.compute(game) -> {ev_per_ticket, ev_minus_price, est_remaining_tickets, sanity_flag}`.
- [ ] Two estimators (per-tier-derived, overall-odds-derived).
- [ ] `sanity_flag` populated when estimators diverge >15%.
- [ ] Unit tests with hand-checked numbers.

## Phase 7 — CLI

- [ ] `fl-scratchers scrape` — full run, writes to SQLite.
- [ ] `fl-scratchers rank [--top N] [--min-price P]` — ranked table (rich).
- [ ] `fl-scratchers diff` — new / removed games vs previous run.
- [ ] `fl-scratchers show <game_id>` — full tier breakdown + EV.
- [ ] `fl-scratchers export --csv out.csv` — latest run to CSV.

## Phase 8 — Polish

- [ ] README quickstart works on a clean clone.
- [ ] Sample output / screenshot in README.
- [ ] One full end-to-end run completes without errors.

## Backlog (post-v1)

- Trend charts over run history.
- Tax-adjusted EV.
- Annuity vs lump-sum modeling for top prizes.
- Second-chance drawing valuation.
- Email/SMS alerts on EV threshold.
- Scheduled runs.
