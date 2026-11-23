"""Turn an invoice file into a validated Invoice, using Claude or a mock."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from .models import INVOICE_JSON_SCHEMA, Invoice

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You extract structured data from invoices for an accounts-payable system.
Return the invoice exactly as written: do not invent line items, and do not fix arithmetic
that looks wrong (a later step flags inconsistencies for human review).
Dates must be YYYY-MM-DD. Currency must be an ISO 4217 code; infer it from symbols
($ -> USD, EUR sign -> EUR, Rs/INR sign -> INR) when no code is printed.
If the document has no tax line, use 0 for tax."""


class ExtractionError(Exception):
    """Raised when an invoice cannot be turned into a valid Invoice."""


class Extractor(Protocol):
    def extract(self, path: Path) -> Invoice: ...


def _content_for(path: Path) -> list[dict]:
    """Build the user-message content blocks for one invoice file."""
    instruction = {"type": "text", "text": "Extract this invoice."}
    if path.suffix.lower() == ".pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        document = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
        return [document, instruction]
    text = path.read_text(encoding="utf-8")
    return [{"type": "text", "text": f"<invoice>\n{text}\n</invoice>"}, instruction]


class ClaudeExtractor:
    """Extracts invoices with the Claude API using a JSON-schema output constraint."""

    def __init__(self, client=None, model: str = MODEL):
        if client is None:
            import anthropic  # imported lazily so mock mode needs no SDK credentials

            client = anthropic.Anthropic()
        self.client = client
        self.model = model

    def extract(self, path: Path) -> Invoice:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            # On a safety decline, the API retries the request on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": "low",  # extraction is a simple task; low effort keeps it fast and cheap
                "format": {"type": "json_schema", "schema": INVOICE_JSON_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _content_for(path)}],
        )
        if response.stop_reason == "refusal":
            raise ExtractionError(f"{path.name}: model declined to process this document")
        if response.stop_reason == "max_tokens":
            raise ExtractionError(f"{path.name}: response was cut off (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ExtractionError(f"{path.name}: no text block in response")
        try:
            return Invoice.model_validate_json(text)
        except ValidationError as exc:
            raise ExtractionError(f"{path.name}: invalid extraction: {exc}") from exc


class MockExtractor:
    """Returns pre-recorded extractions from samples/expected/<name>.json (no API key needed)."""

    def __init__(self, expected_dir: Path):
        self.expected_dir = expected_dir

    def extract(self, path: Path) -> Invoice:
        fixture = self.expected_dir / f"{path.stem}.json"
        if not fixture.exists():
            raise ExtractionError(f"{path.name}: no mock fixture at {fixture}")
        return Invoice.model_validate(json.loads(fixture.read_text(encoding="utf-8")))
