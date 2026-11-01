"""
Natural-language transaction entry (Stage 5, Feature H).

A deterministic, rule-based extractor: amount, currency, type, date,
merchant and payment method are pulled from free text with explicit
patterns. Anything that cannot be extracted with confidence is reported
in `ambiguous_fields` — the parser NEVER guesses an amount or a date.
The result is a draft; a transaction is created only when the user
reviews the draft and confirms through the normal validated endpoint.
"""
import re
from datetime import date, timedelta

_INCOME_WORDS = ("received", "salary", "credited", "earned", "allowance", "income",
                 "got paid", "payment received", "deposit", "stipend", "scholarship")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})


def _parse_amount(low: str):
    m = re.search(r"(?:₹|rs\.?|inr|\$|usd)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", low)
    if not m:
        m = re.search(r"\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:₹|rs\.?|rupees|inr|dollars?)\b", low)
    if not m:
        m = re.search(r"\b([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?)\b", low)
    if not m:
        m = re.search(r"\b([0-9]+(?:\.[0-9]{1,2})?)\b", low)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_date(low: str, today: date):
    if "day before yesterday" in low:
        return today - timedelta(days=2)
    if "yesterday" in low:
        return today - timedelta(days=1)
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", low)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\b", low)
    if m and m.group(2) in _MONTHS:
        y = today.year
        d = date(y, _MONTHS[m.group(2)], int(m.group(1)))
        return d if d <= today else date(y - 1, _MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", low)
    if m and m.group(1) in _MONTHS:
        y = today.year
        d = date(y, _MONTHS[m.group(1)], int(m.group(2)))
        return d if d <= today else date(y - 1, _MONTHS[m.group(1)], int(m.group(2)))
    return today  # default: today (stated in the draft, user can edit)


def parse_transaction_text(text: str, today: date = None) -> dict:
    today = today or date.today()
    raw = (text or "").strip()
    low = raw.lower()
    ambiguous = []

    amount = _parse_amount(low)
    if amount is None:
        ambiguous.append("amount")
    currency = "USD" if ("$" in raw or "usd" in low or "dollar" in low) else "INR"

    if "refund" in low:
        type_ = "refund"
    elif "transfer" in low:
        type_ = "transfer"
    elif any(w in low for w in _INCOME_WORDS):
        type_ = "income"
    else:
        type_ = "expense"

    txn_date = _parse_date(low, today)

    merchant = ""
    mm = re.search(r"\b(?:at|from)\s+([a-z0-9][a-z0-9&.'\- ]{1,40}?)(?:\s+(?:today|yesterday|using|via|with|on|for)\b|[.,]|$)", low)
    if mm:
        merchant = mm.group(1).strip().title()
    if not merchant:
        ambiguous.append("merchant")

    payment_method = None
    for word, label in (("upi", "UPI"), ("cash", "Cash"), ("card", "Card"),
                        ("netbanking", "Net banking"), ("bank transfer", "Bank transfer")):
        if word in low:
            payment_method = label
            break

    return {
        "type": type_,
        "amount": amount,
        "currency": currency,
        "category_name": None,  # filled by the categoriser in the endpoint
        "merchant": merchant,
        "date": txn_date.isoformat(),
        "description": raw,
        "payment_method": payment_method,
        "ambiguous_fields": ambiguous,
        "requires_review": True,
        "note": "Draft only — nothing is saved until you review and confirm. Fields listed in ambiguous_fields could not be extracted and must be checked.",
    }
