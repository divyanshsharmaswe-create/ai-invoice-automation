"""Command-line entry point: `invoice-automation --mock` or `python -m invoice_automation`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .extractor import ClaudeExtractor, MockExtractor
from .pipeline import find_invoices, run
from .sinks import CsvSink, GoogleSheetSink, SlackAlerter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract invoices with Claude → Sheets/CSV → Slack.")
    parser.add_argument("--input", type=Path, default=Path("samples"), help="folder of invoices")
    parser.add_argument("--output", type=Path, default=Path("out/invoices.csv"), help="CSV output path")
    parser.add_argument("--mock", action="store_true", help="use recorded extractions; no API keys needed")
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(os.environ.get("ALERT_THRESHOLD", "5000")),
        help="alert on invoices with total >= this amount",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    files = find_invoices(args.input)
    if not files:
        print(f"No invoices found in {args.input}", file=sys.stderr)
        return 1

    if args.mock:
        extractor = MockExtractor(args.input / "expected")
    else:
        extractor = ClaudeExtractor()

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if sheet_id and creds and not args.mock:
        sink = GoogleSheetSink(sheet_id, creds)
        destination = f"Google Sheet {sheet_id}"
    else:
        sink = CsvSink(args.output)
        destination = str(args.output)

    alerter = SlackAlerter(os.environ.get("SLACK_WEBHOOK_URL"), threshold=args.threshold, dry_run=args.mock)

    mode = "mock" if args.mock else "claude"
    print(f"Processing {len(files)} invoice(s) from {args.input} [{mode} mode]\n")
    summary = run(files, extractor, sink, alerter)

    for item in summary.processed:
        inv = item.invoice
        flag = "  ⚠ needs review" if item.needs_review else ""
        print(f"✔ {item.source_file:<28} {inv.vendor:<28} {inv.currency} {inv.total:>10,.2f}{flag}")
    for name, error in summary.failed.items():
        print(f"✘ {name:<28} {error}")

    print(
        f"\n{len(summary.processed)} saved to {destination}, "
        f"{summary.alerts} Slack alert(s), {len(summary.failed)} failed"
    )
    return 0 if not summary.failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
