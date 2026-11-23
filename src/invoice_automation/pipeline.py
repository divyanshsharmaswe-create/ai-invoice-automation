"""Glue: extract → validate → store → alert."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .extractor import ExtractionError, Extractor
from .models import ProcessedInvoice
from .sinks import RowSink, SlackAlerter

SUPPORTED_SUFFIXES = {".txt", ".eml", ".md", ".pdf"}


@dataclass
class RunSummary:
    processed: list[ProcessedInvoice] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    alerts: int = 0


def find_invoices(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)


def run(files: list[Path], extractor: Extractor, sink: RowSink, alerter: SlackAlerter) -> RunSummary:
    summary = RunSummary()
    for path in files:
        try:
            invoice = extractor.extract(path)
        except ExtractionError as exc:
            summary.failed[path.name] = str(exc)
            continue
        issues = invoice.consistency_issues()
        processed = ProcessedInvoice(
            source_file=path.name, invoice=invoice, needs_review=bool(issues), issues=issues
        )
        sink.append(processed)
        if alerter.maybe_alert(processed):
            summary.alerts += 1
        summary.processed.append(processed)
    return summary
