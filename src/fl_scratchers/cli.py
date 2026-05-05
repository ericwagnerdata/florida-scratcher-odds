"""CLI entry point. Subcommands: scrape, rank, diff, show, export."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from . import ev as ev_mod
from . import scrape, storage
from .parse import parse_detail, parse_list_item

console = Console()


def cmd_scrape(args: argparse.Namespace) -> int:
    storage.init_db(args.db)
    session = scrape.make_session()

    console.print("[bold]Fetching game list...[/]")
    raw_list = scrape.list_games(session)
    games = [parse_list_item(item) for item in raw_list]
    console.print(f"  AEM listing: [cyan]{len(games)}[/] games")

    console.print("[bold]Fetching top-remaining (validation list)...[/]")
    raw_top = scrape.list_top_remaining(session)
    active_ids = {int(g["Id"]) for g in raw_top}
    console.print(f"  validated active: [cyan]{len(active_ids)}[/] games")

    with storage.connect(args.db) as conn:
        run_id = storage.start_run(conn)
        console.print(f"  run_id = [cyan]{run_id}[/]")

        succeeded = 0
        failed = 0
        skipped_inactive = 0
        active_games = [g for g in games if g["game_id"] in active_ids]
        inactive_games = [g for g in games if g["game_id"] not in active_ids]

        # Record inactive games immediately (no API call needed).
        for stub in inactive_games:
            storage.write_snapshot(
                conn,
                run_id,
                game_id=stub["game_id"],
                name=stub["name"],
                ticket_price=stub["ticket_price"],
                overall_odds=None,
                launch_date=None,
                end_date=None,
                redemption_date=None,
                status="inactive",
                tiers=None,
                ev_per_ticket=None,
                ev_minus_price=None,
                est_tickets_remaining=None,
                sanity_flag=None,
            )
            skipped_inactive += 1

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching detail...", total=len(active_games))
            for stub in active_games:
                gid = stub["game_id"]
                progress.update(task, description=f"#{gid} {stub['name'][:40]}")
                try:
                    payload = scrape.fetch_detail(gid, session=session)
                    if not isinstance(payload, dict) or not payload.get("OddsTiers"):
                        storage.write_snapshot(
                            conn,
                            run_id,
                            game_id=gid,
                            name=stub["name"],
                            ticket_price=stub["ticket_price"],
                            overall_odds=None,
                            launch_date=None,
                            end_date=None,
                            redemption_date=None,
                            status="no_detail",
                            tiers=None,
                            ev_per_ticket=None,
                            ev_minus_price=None,
                            est_tickets_remaining=None,
                            sanity_flag=None,
                        )
                        progress.advance(task)
                        scrape.jitter_sleep()
                        continue
                    game = parse_detail(payload)
                    result = ev_mod.compute(game)
                    storage.write_snapshot(
                        conn,
                        run_id,
                        game_id=game.game_id,
                        name=game.name,
                        ticket_price=game.ticket_price,
                        overall_odds=game.overall_odds,
                        launch_date=game.launch_date,
                        end_date=game.end_date,
                        redemption_date=game.redemption_date,
                        status="active",
                        tiers=[asdict(t) for t in game.tiers],
                        ev_per_ticket=result.ev_per_ticket,
                        ev_minus_price=result.ev_minus_price,
                        est_tickets_remaining=result.est_tickets_remaining,
                        sanity_flag=result.sanity_flag,
                    )
                    succeeded += 1
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    storage.write_snapshot(
                        conn,
                        run_id,
                        game_id=gid,
                        name=stub["name"],
                        ticket_price=stub["ticket_price"],
                        overall_odds=None,
                        launch_date=None,
                        end_date=None,
                        redemption_date=None,
                        status=f"fetch_failed: {type(e).__name__}",
                        tiers=None,
                        ev_per_ticket=None,
                        ev_minus_price=None,
                        est_tickets_remaining=None,
                        sanity_flag=None,
                    )
                    console.print(f"  [red]fetch failed for #{gid}: {e}[/]")
                progress.advance(task)
                scrape.jitter_sleep()

        storage.finish_run(conn, run_id, succeeded)

    console.print(
        f"[bold green]done[/] — {succeeded} active, {skipped_inactive} inactive, "
        f"{failed} failed, run_id={run_id}"
    )
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        run_id = storage.latest_run_id(conn)
        if run_id is None:
            console.print("[red]No completed runs. Run `fl-scratchers scrape` first.[/]")
            return 1
        rows = storage.snapshots_for_run(conn, run_id)

    rows = [r for r in rows if r["ev_per_ticket"] is not None]
    if args.min_price is not None:
        rows = [r for r in rows if (r["ticket_price"] or 0) >= args.min_price]

    rows.sort(key=lambda r: (r["ev_per_ticket"] or 0) / (r["ticket_price"] or 1), reverse=True)
    if args.top:
        rows = rows[: args.top]

    table = Table(title=f"Ranked games (run {run_id}, by return rate)")
    table.add_column("ID", justify="right")
    table.add_column("Name")
    table.add_column("Price", justify="right")
    table.add_column("EV/ticket", justify="right")
    table.add_column("EV - price", justify="right")
    table.add_column("Return", justify="right")
    table.add_column("Top rem.", justify="right")
    table.add_column("Flag")

    for r in rows:
        ev = r["ev_per_ticket"]
        diff = r["ev_minus_price"]
        price = r["ticket_price"] or 0
        ret = ev / price if price else 0
        tiers = json.loads(r["tiers_json"]) if r["tiers_json"] else []
        top_remaining = tiers[0]["remaining"] if tiers else 0
        diff_color = "green" if diff > 0 else "red"
        table.add_row(
            str(r["game_id"]),
            (r["name"] or "")[:40],
            f"${price:.0f}",
            f"${ev:.2f}",
            f"[{diff_color}]${diff:+.2f}[/]",
            f"{ret * 100:.1f}%",
            str(top_remaining),
            r["sanity_flag"] or "",
        )

    console.print(table)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        latest = storage.latest_run_id(conn)
        previous = storage.previous_run_id(conn)
        if latest is None:
            console.print("[red]No runs.[/]")
            return 1
        if previous is None:
            console.print(f"Only one run ([cyan]{latest}[/]). Nothing to diff.")
            return 0

        latest_rows = {r["game_id"]: r for r in storage.snapshots_for_run(conn, latest)}
        prev_rows = {r["game_id"]: r for r in storage.snapshots_for_run(conn, previous)}

    new_ids = set(latest_rows) - set(prev_rows)
    gone_ids = set(prev_rows) - set(latest_rows)

    console.print(f"Comparing run [cyan]{previous}[/] → [cyan]{latest}[/]")
    if new_ids:
        console.print("\n[bold green]New games:[/]")
        for gid in sorted(new_ids):
            console.print(f"  #{gid}  {latest_rows[gid]['name']}")
    if gone_ids:
        console.print("\n[bold red]Gone:[/]")
        for gid in sorted(gone_ids):
            console.print(f"  #{gid}  {prev_rows[gid]['name']}")
    if not new_ids and not gone_ids:
        console.print("[dim]No changes in game roster.[/]")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        run_id = storage.latest_run_id(conn)
        if run_id is None:
            console.print("[red]No runs.[/]")
            return 1
        row = storage.snapshot_for_game(conn, run_id, args.game_id)
    if row is None:
        console.print(f"[red]Game {args.game_id} not in latest run.[/]")
        return 1

    console.print(f"[bold]#{row['game_id']}  {row['name']}[/]")
    console.print(f"  price: ${row['ticket_price']:.0f}   overall odds: 1-in-{row['overall_odds']}")
    console.print(f"  launch: {row['launch_date']}   end: {row['end_date']}")
    if row["ev_per_ticket"] is not None:
        console.print(
            f"  EV/ticket: [bold]${row['ev_per_ticket']:.2f}[/]   "
            f"EV - price: ${row['ev_minus_price']:+.2f}   "
            f"est tickets remaining: {row['est_tickets_remaining']:,.0f}"
        )
    if row["sanity_flag"]:
        console.print(f"  [yellow]flag: {row['sanity_flag']}[/]")

    tiers = json.loads(row["tiers_json"]) if row["tiers_json"] else []
    if tiers:
        t = Table(title="Prize tiers")
        t.add_column("Prize", justify="right")
        t.add_column("Odds", justify="right")
        t.add_column("Total", justify="right")
        t.add_column("Remaining", justify="right")
        t.add_column("Paid", justify="right")
        for tier in tiers:
            t.add_row(
                f"${float(tier['prize_amount']):,.2f}",
                f"1-in-{tier['odds_1_in']:,}",
                f"{tier['total_printed']:,}",
                f"{tier['remaining']:,}",
                f"{tier['paid']:,}",
            )
        console.print(t)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with storage.connect(args.db) as conn:
        run_id = storage.latest_run_id(conn)
        if run_id is None:
            console.print("[red]No runs.[/]")
            return 1
        rows = storage.snapshots_for_run(conn, run_id)

    sorted_rows = sorted(
        rows,
        key=lambda r: r["ev_per_ticket"] if r["ev_per_ticket"] is not None else float("-inf"),
        reverse=True,
    )

    out = Path(args.csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "game_id", "name", "ticket_price", "overall_odds",
                "launch_date", "end_date", "status",
                "ev_per_ticket", "ev_minus_price", "return_rate",
                "est_tickets_remaining", "sanity_flag",
            ]
        )
        for r in sorted_rows:
            ev = r["ev_per_ticket"]
            price = r["ticket_price"]
            ret = (ev / price) if (ev is not None and price) else None
            w.writerow(
                [
                    r["game_id"], r["name"], price, r["overall_odds"],
                    r["launch_date"], r["end_date"], r["status"],
                    ev, r["ev_minus_price"],
                    f"{ret:.4f}" if ret is not None else "",
                    r["est_tickets_remaining"], r["sanity_flag"],
                ]
            )
    console.print(f"wrote [cyan]{out}[/] ({len(rows)} rows)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fl-scratchers")
    p.add_argument("--db", default=str(storage.DEFAULT_DB), help="SQLite DB path")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("scrape", help="Fetch all games and store a new run")

    pr = sub.add_parser("rank", help="Rank games in the latest run by EV")
    pr.add_argument("--top", type=int, default=None, help="Show only top N")
    pr.add_argument("--min-price", type=float, default=None, help="Filter by min price")

    sub.add_parser("diff", help="Show new/gone games vs previous run")

    ps = sub.add_parser("show", help="Show full tier breakdown for one game")
    ps.add_argument("game_id", type=int)

    pe = sub.add_parser("export", help="Export latest run to CSV")
    pe.add_argument("csv", help="Output CSV path")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "scrape": cmd_scrape,
        "rank": cmd_rank,
        "diff": cmd_diff,
        "show": cmd_show,
        "export": cmd_export,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
