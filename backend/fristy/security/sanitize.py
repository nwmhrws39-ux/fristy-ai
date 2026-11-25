"""Detection and redaction of sensitive data, and untrusted-content fencing."""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{30,})\b")),
    ("github_token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,})\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "password_assignment",
        re.compile(
            r"(?i)\b(password|passwd|pwd|passcode|pin|secret|api[_ ]?key|token|סיסמה|סיסמא|קוד סודי)\b\s*(is|=|:|הוא|היא)?\s*\S+"
        ),
    ),
    ("password_hebrew", re.compile(r"(סיסמ[הא]|קוד\s+סודי|קוד\s+גישה)[^\n]{0,15}?(?:היא|הוא|:|=)\s*\S+")),
]

_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def find_sensitive(text: str) -> list[str]:
    """Return the kinds of sensitive data detected in ``text``."""
    found: list[str] = []
    if not text:
        return found
    for name, pat in _PATTERNS:
        if pat.search(text):
            found.append(name)
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found.append("payment_card")
            break
    return found


def contains_sensitive(text: str) -> bool:
    return bool(find_sensitive(text))


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for name, pat in _PATTERNS:
        if name in ("password_assignment", "password_hebrew"):
            out = pat.sub(lambda m: m.group(1) + ": [REDACTED]", out)
        else:
            out = pat.sub("[REDACTED]", out)

    def _card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[REDACTED-CARD]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group(0)

    return _CARD.sub(_card, out)


UNTRUSTED_OPEN = "<<<UNTRUSTED_CONTENT source=\"{source}\">>>"
UNTRUSTED_CLOSE = "<<<END_UNTRUSTED_CONTENT>>>"


def fence_untrusted(text: str, source: str) -> str:
    """Wrap content that came from the screen, files or the web.

    The system prompt instructs the model that anything inside these markers is
    data, never instructions. We also strip any attempt to forge the markers.
    """
    cleaned = (text or "").replace("<<<", "‹‹‹").replace(">>>", "›››")
    return f"{UNTRUSTED_OPEN.format(source=source)}\n{cleaned}\n{UNTRUSTED_CLOSE}"
