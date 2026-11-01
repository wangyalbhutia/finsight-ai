import re
# Transaction merchant/description text is DATA, never instructions.
# Strip prompt-injection patterns before any text reaches LLM context.
_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)?\s*instructions?",
    r"disregard\s+.*", r"reveal\s+.*", r"system\s+prompt.*", r"you\s+are\s+now\s+.*",
    r"forget\s+(all|everything).*", r"override\s+.*", r"jailbreak.*",
    r"act\s+as\s+.*", r"send\s+.*\s+to\s+.*", r"delete\s+all.*", r"create\s+a?\s*transaction.*",
]
def sanitize_text(text: str) -> str:
    if not text:
        return ""
    out = str(text)
    for p in _PATTERNS:
        out = re.sub(p, "[redacted]", out, flags=re.IGNORECASE)
    # strip control chars, cap length
    out = re.sub(r"[\x00-\x1f\x7f]", " ", out)[:200]
    return out.strip()

def is_injection(text: str) -> bool:
    return sanitize_text(text) != (text or "").strip()
