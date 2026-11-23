"""Destinations for processed invoices: CSV, Google Sheets, Slack alerts."""

from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path
from typing import Protocol

from .models import ProcessedInvoice

COLUMNS = [
    "source_file",
    "vendor",
    "invoice_number",
    "invoice_date",
    "currency",
    "subtotal",
    "tax",
    "total",
    "line_item_count",
    "needs_review",
    "issues",
]


def to_row(processed: ProcessedInvoice) -> list[str]:
    inv = processed.invoice
    return [
        processed.source_file,
        inv.vendor,
        inv.invoice_number,
        inv.invoice_date.isoformat(),
        inv.currency,
        f"{inv.subtotal:.2f}",
        f"{inv.tax:.2f}",
        f"{inv.total:.2f}",
        str(len(inv.line_items)),
        "yes" if processed.needs_review else "no",
        "; ".join(processed.issues),
    ]


class RowSink(Protocol):
    def append(self, processed: ProcessedInvoice) -> None: ...


class CsvSink:
    def __init__(self, path: Path):
        self.path = path

    def append(self, processed: ProcessedInvoice) -> None:
        new_file = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if new_file:
                writer.writerow(COLUMNS)
            writer.writerow(to_row(processed))


class GoogleSheetSink:
    """Appends rows to the first worksheet of a Google Sheet (service-account auth)."""

    def __init__(self, sheet_id: str, credentials_file: str):
        import gspread  # optional dependency: pip install '.[sheets]'

        client = gspread.service_account(filename=credentials_file)
        self.worksheet = client.open_by_key(sheet_id).sheet1
        if not self.worksheet.row_values(1):
            self.worksheet.append_row(COLUMNS)

    def append(self, processed: ProcessedInvoice) -> None:
        self.worksheet.append_row(to_row(processed), value_input_option="USER_ENTERED")


class SlackAlerter:
    """Posts a message for invoices above a threshold or flagged for review."""

    def __init__(self, webhook_url: str | None, threshold: float, dry_run: bool = False):
        self.webhook_url = webhook_url
        self.threshold = threshold
        self.dry_run = dry_run or not webhook_url
        self.sent: list[str] = []

    def should_alert(self, processed: ProcessedInvoice) -> bool:
        return processed.needs_review or processed.invoice.total >= self.threshold

    def message_for(self, processed: ProcessedInvoice) -> str:
        inv = processed.invoice
        reason = "needs review" if processed.needs_review else f"over {self.threshold:,.0f}"
        text = (
            f":rotating_light: Invoice {inv.invoice_number} from {inv.vendor}: "
            f"{inv.currency} {inv.total:,.2f} ({reason})"
        )
        if processed.issues:
            text += "\n• " + "\n• ".join(processed.issues)
        return text

    def maybe_alert(self, processed: ProcessedInvoice) -> bool:
        if not self.should_alert(processed):
            return False
        text = self.message_for(processed)
        self.sent.append(text)
        if self.dry_run:
            print(f"[slack dry-run] {text}")
            return True
        body = json.dumps({"text": text}).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310 (trusted URL from config)
            resp.read()
        return True
