"""Command-line deal finder — scan the best deals fast from the terminal.

  python -m dealfinder.cli deals --city Dubai --min-score 40 --limit 20
  python -m dealfinder.cli deals --max-price 1500000 --min-yield 6 --type apartment
  python -m dealfinder.cli seed          # (re)generate sample data
"""

from __future__ import annotations

import argparse

import pandas as pd
from rich.console import Console
from rich.table import Table

from .config import Config
from .pipeline import find_deals

console = Console()

DISPLAY_COLS = [
    ("deal_score", "Score"),
    ("city", "City"),
    ("area", "Area"),
    ("property_type", "Type"),
    ("bedrooms", "Bed"),
    ("size_sqft", "Sqft"),
    ("price", "Price (AED)"),
    ("discount_pct", "Disc %"),
    ("net_yield_pct", "Net Yld %"),
    ("confidence", "Conf"),
    ("source", "Source"),
    ("flags", "Flags"),
]


def _apply_filters(df: pd.DataFrame, args) -> pd.DataFrame:
    if args.city:
        df = df[df["city"].str.lower() == args.city.lower()]
    if args.type:
        df = df[df["property_type"].str.lower() == args.type.lower()]
    if args.source:
        df = df[df["source"].str.lower() == args.source.lower()]
    if args.max_price is not None:
        df = df[df["price"] <= args.max_price]
    if args.min_score is not None:
        df = df[df["deal_score"] >= args.min_score]
    if args.min_yield is not None:
        df = df[df["net_yield_pct"] >= args.min_yield]
    if args.min_discount is not None:
        df = df[df["discount_pct"] >= args.min_discount]
    if not args.include_suspicious:
        df = df[~df["flags"].str.contains("suspicious-discount", na=False)]
    return df


def _render(df: pd.DataFrame, limit: int) -> None:
    table = Table(title=f"Top {min(limit, len(df))} UAE property deals", header_style="bold cyan")
    for _, label in DISPLAY_COLS:
        table.add_column(label)
    for _, row in df.head(limit).iterrows():
        cells = []
        for col, _ in DISPLAY_COLS:
            val = row[col]
            if col == "price":
                val = f"{int(val):,}"
            elif col in ("discount_pct", "net_yield_pct") and pd.notna(val):
                val = f"{val:.1f}"
            cells.append("" if pd.isna(val) else str(val))
        score = row["deal_score"]
        style = "bold green" if score >= 55 else "yellow" if score >= 35 else None
        table.add_row(*cells, style=style)
    console.print(table)


def cmd_deals(args) -> None:
    cfg = Config.load(args.config) if args.config else Config.load()
    deals = find_deals(cfg)
    if deals.empty:
        console.print("[red]No listings scored. Did you seed or wire data?[/red]")
        return
    filtered = _apply_filters(deals, args)
    if filtered.empty:
        console.print("[yellow]No deals match those filters.[/yellow]")
        return
    _render(filtered, args.limit)
    console.print(
        f"\n[dim]{len(filtered)} of {len(deals)} listings matched. "
        f"Score = 55% undervaluation + 45% net yield, scaled by comp confidence.[/dim]"
    )
    if args.save:
        from pathlib import Path
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        filtered.to_csv(args.save, index=False)
        console.print(f"[green]Saved {len(filtered)} rows to {args.save}[/green]")


def cmd_seed(args) -> None:
    from scripts.seed_sample_data import main as seed_main
    seed_main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dealfinder", description="Find UAE property deals fast.")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("deals", help="Score listings and show the best deals.")
    d.add_argument("--city", help="Dubai or Abu Dhabi")
    d.add_argument("--type", help="apartment | villa | townhouse | penthouse")
    d.add_argument("--source", help="bayut | dubizzle | property_finder | reddit")
    d.add_argument("--max-price", type=float, help="Max asking price (AED)")
    d.add_argument("--min-score", type=float, help="Min deal score (0-100)")
    d.add_argument("--min-yield", type=float, help="Min net rental yield (%)")
    d.add_argument("--min-discount", type=float, help="Min discount to comps (%)")
    d.add_argument("--limit", type=int, default=20, help="Rows to show")
    d.add_argument("--include-suspicious", action="store_true",
                   help="Include too-good-to-be-true discounts (default: hidden)")
    d.add_argument("--save", help="Write filtered results to a CSV path")
    d.add_argument("--config", help="Path to config.yaml")
    d.set_defaults(func=cmd_deals)

    s = sub.add_parser("seed", help="Generate sample data.")
    s.set_defaults(func=cmd_seed)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
