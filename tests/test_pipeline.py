import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from invoice_automation.cli import main
from invoice_automation.extractor import ClaudeExtractor, ExtractionError, MockExtractor
from invoice_automation.models import Invoice
from invoice_automation.pipeline import find_invoices, run
from invoice_automation.sinks import CsvSink, SlackAlerter

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def load_fixture(name: str) -> dict:
    return json.loads((SAMPLES / "expected" / f"{name}.json").read_text())


def test_consistent_invoice_has_no_issues():
    invoice = Invoice.model_validate(load_fixture("acme-cloud-2026-11"))
    assert invoice.consistency_issues() == []


def test_subtotal_mismatch_is_flagged():
    invoice = Invoice.model_validate(load_fixture("quickprint-supplies"))
    issues = invoice.consistency_issues()
    assert len(issues) == 1
    assert "27800.00" in issues[0] and "28300.00" in issues[0]


def test_mock_pipeline_writes_csv_and_alerts(tmp_path):
    out = tmp_path / "invoices.csv"
    alerter = SlackAlerter(webhook_url=None, threshold=5000, dry_run=True)
    summary = run(find_invoices(SAMPLES), MockExtractor(SAMPLES / "expected"), CsvSink(out), alerter)

    assert len(summary.processed) == 3
    assert summary.failed == {}
    rows = list(csv.DictReader(out.open()))
    assert [r["invoice_number"] for r in rows] == ["AC-20931", "BP-0457", "QP/26/1187"]
    # BrightPath (EUR 11,424) and QuickPrint (INR 33,394, also flagged) are over 5,000; Acme is not.
    assert summary.alerts == 2
    assert rows[2]["needs_review"] == "yes"


def test_cli_mock_mode(tmp_path, capsys):
    out = tmp_path / "out.csv"
    code = main(["--mock", "--input", str(SAMPLES), "--output", str(out)])
    assert code == 0
    assert out.exists()
    assert "3 saved" in capsys.readouterr().out


def fake_response(text: str | None, stop_reason: str = "end_turn"):
    content = [] if text is None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=content)


class FakeClient:
    def __init__(self, response):
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._response = response

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_claude_extractor_parses_structured_output():
    client = FakeClient(fake_response(json.dumps(load_fixture("acme-cloud-2026-11"))))
    invoice = ClaudeExtractor(client=client).extract(SAMPLES / "acme-cloud-2026-11.txt")

    assert invoice.vendor == "Acme Cloud Hosting LLC"
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default"
    assert "ACME CLOUD HOSTING" in call["messages"][0]["content"][0]["text"]


def test_claude_extractor_sends_pdf_as_document(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    client = FakeClient(fake_response(json.dumps(load_fixture("acme-cloud-2026-11"))))
    ClaudeExtractor(client=client).extract(pdf)
    block = client.calls[0]["messages"][0]["content"][0]
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (fake_response(None, stop_reason="refusal"), "declined"),
        (fake_response('{"vendor": "x"}', stop_reason="max_tokens"), "cut off"),
        (fake_response('{"vendor": "x"}'), "invalid extraction"),
    ],
)
def test_claude_extractor_errors(response, message):
    with pytest.raises(ExtractionError, match=message):
        ClaudeExtractor(client=FakeClient(response)).extract(SAMPLES / "acme-cloud-2026-11.txt")
