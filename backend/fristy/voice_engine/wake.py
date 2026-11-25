"""Wake-phrase matching on locally transcribed audio ("Hey Fristy" / "היי פריסטי")."""
from __future__ import annotations

import difflib
import re
import unicodedata

# Common Whisper mis-hearings of the brand name.
NAME_VARIANTS = {"fristy", "fristi", "fristy", "fristie", "fristee", "fristey", "frosty", "christy", "kristy",
                 "feisty", "thirsty", "fresty", "pristy", "פריסטי", "פריסתי", "פרסטי", "פריסטיי"}
GREETINGS = {"hey", "hi", "hello", "ok", "okay", "a", "hay", "היי", "הי", "הייי", "שלום", "אהלן", "יו"}


def _words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[^\w֐-׿\s']", " ", t)
    return t.split()


def detect_wake(text: str, phrases: list[str], threshold: float = 0.75) -> tuple[bool, str]:
    """Return (detected, remaining_command_text)."""
    words = _words(text)
    if not words:
        return False, ""
    # 1) greeting + name variant in the first three words
    for i, w in enumerate(words[:3]):
        name_like = w in NAME_VARIANTS or max(difflib.SequenceMatcher(None, w, v).ratio() for v in NAME_VARIANTS) >= 0.8
        if name_like and (i == 0 or words[i - 1] in GREETINGS or i <= 1):
            return True, " ".join(words[i + 1:])
    # 2) fuzzy match against configured phrases
    for p in phrases:
        pw = _words(p)
        if not pw:
            continue
        head = " ".join(words[: len(pw)])
        if difflib.SequenceMatcher(None, head, " ".join(pw)).ratio() >= threshold:
            return True, " ".join(words[len(pw):])
    return False, ""
