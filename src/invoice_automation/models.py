"""Data models for extracted invoices."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# Tolerance (in currency units) when checking that line items add up.
SUM_TOLERANCE = 0.05


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class Invoice(BaseModel):
    vendor: str
    invoice_number: str
    invoice_date: date
    currency: str = Field(description="ISO 4217 code, e.g. USD")
    line_items: list[LineItem]
    subtotal: float
    tax: float
    total: float

    def consistency_issues(self) -> list[str]:
        """Return human-readable problems; an empty list means the numbers add up."""
        issues: list[str] = []
        items_sum = round(sum(item.amount for item in self.line_items), 2)
        if abs(items_sum - self.subtotal) > SUM_TOLERANCE:
            issues.append(f"line items sum to {items_sum:.2f} but subtotal is {self.subtotal:.2f}")
        if abs(self.subtotal + self.tax - self.total) > SUM_TOLERANCE:
            issues.append(f"subtotal + tax = {self.subtotal + self.tax:.2f} but total is {self.total:.2f}")
        return issues


class ProcessedInvoice(BaseModel):
    source_file: str
    invoice: Invoice
    needs_review: bool
    issues: list[str]


# JSON Schema sent to Claude as a structured-output constraint.
# Hand-written (no $refs) so it maps 1:1 onto the Invoice model above.
INVOICE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string"},
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
        "currency": {"type": "string", "description": "ISO 4217 code, e.g. USD"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "amount": {"type": "number"},
                },
                "required": ["description", "quantity", "unit_price", "amount"],
                "additionalProperties": False,
            },
        },
        "subtotal": {"type": "number"},
        "tax": {"type": "number"},
        "total": {"type": "number"},
    },
    "required": [
        "vendor",
        "invoice_number",
        "invoice_date",
        "currency",
        "line_items",
        "subtotal",
        "tax",
        "total",
    ],
    "additionalProperties": False,
}
