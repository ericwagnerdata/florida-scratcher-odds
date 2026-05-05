# florida-scratcher-odds

A tool for evaluating Florida Lottery scratch-off games by their **expected value (EV)**, based on the prizes still remaining in each game.

## Why

Scratch-off games are not all created equal. As tickets get sold and prizes get claimed, a game's real expected value drifts away from the odds printed on the back. A game with most of its top prizes already claimed is worse than its advertised odds suggest; a brand-new game with the full prize pool intact is at its peak.

This tool scrapes the [Florida Lottery scratch-off pages](https://floridalottery.com/games/scratch-offs/top-remaining-prizes), pulls the current remaining-prize counts for every active game, and ranks them by expected value per ticket so you can see which games are actually worth playing.

## What it does

- Pulls the active-game list and per-game prize tier tables (price, overall odds, prize amounts, prizes remaining, odds per tier).
- Estimates tickets remaining from the published odds and remaining-prize counts.
- Computes expected value per ticket and ranks games.
- Stores each run in a local SQLite database so you can see when new games launch or existing games end.

## Usage (planned)

```bash
fl-scratchers scrape         # refresh data from floridalottery.com
fl-scratchers rank           # ranked table of best EV
fl-scratchers diff           # new / removed games since last run
fl-scratchers show <id>      # full prize tier breakdown for one game
fl-scratchers export --csv   # dump latest run to CSV
```

## Status

Early development. See [PRD.md](PRD.md) for the design and build plan.

## Disclaimer

This is an analysis tool, not betting advice. Even a +EV scratch-off is a high-variance gamble — the EV is a long-run average, and your actual outcome on any given ticket is overwhelmingly likely to be a loss. Play responsibly.
