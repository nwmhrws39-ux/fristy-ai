"""Fast, offline intent matching for very common one-shot commands (English + Hebrew).

Deliberately conservative: patterns must match the WHOLE utterance, so anything
compound or ambiguous goes to the AI model instead.
"""
from __future__ import annotations

import re
from typing import Optional

_NUM = r"(\d{1,3})\s*(?:%|percent|אחוז(?:ים)?)?"
_P = [
    (re.compile(rf"^(?:please\s+)?(?:set\s+)?(?:the\s+)?volume\s+(?:to\s+|at\s+)?{_NUM}$", re.I), "set_volume"),
    (re.compile(rf"^(?:תגדיר|הגדר|שנה|תשנה|קבע|תקבע)?\s*(?:את\s+)?(?:ה)?(?:ווליום|עוצמה|עוצמת\s+(?:ה)?(?:קול|שמע))\s+(?:ל-?|על\s+)?{_NUM}$"), "set_volume"),
    (re.compile(r"^(?:please\s+)?(?:mute)(?:\s+(?:the\s+)?(?:sound|volume|audio))?$", re.I), "mute"),
    (re.compile(r"^(?:תשתיק|השתק)(?:\s+את\s+(?:ה)?(?:קול|סאונד))?$"), "mute"),
    (re.compile(r"^(?:please\s+)?unmute(?:\s+(?:the\s+)?(?:sound|volume|audio))?$", re.I), "unmute"),
    (re.compile(r"^(?:בטל\s+השתקה|תבטל\s+השתקה)$"), "unmute"),
    (re.compile(r"^(?:please\s+)?lock\s+(?:the\s+|my\s+)?(?:computer|pc|screen)$", re.I), "lock"),
    (re.compile(r"^(?:נעל|תנעל)\s+(?:את\s+)?(?:ה)?(?:מחשב|מסך)$"), "lock"),
    (re.compile(r"^(?:please\s+)?take\s+a\s+screenshot$", re.I), "screenshot"),
    (re.compile(r"^(?:צלם|תצלם)\s+(?:את\s+)?(?:ה)?מסך$"), "screenshot"),
    (re.compile(r"^(?:next\s+(?:song|track)|skip(?:\s+(?:song|track))?)$", re.I), "next"),
    (re.compile(r"^(?:שיר\s+הבא|השיר\s+הבא|דלג)$"), "next"),
    (re.compile(r"^(?:previous\s+(?:song|track))$", re.I), "previous"),
    (re.compile(r"^(?:שיר\s+קודם|השיר\s+הקודם)$"), "previous"),
    (re.compile(r"^(?:pause|play|resume)(?:\s+(?:the\s+)?(?:music|media|song))?$", re.I), "play_pause"),
    (re.compile(r"^(?:עצור|נגן|תמשיך)\s+(?:את\s+)?(?:ה)?(?:מוזיקה|שיר)$"), "play_pause"),
    (re.compile(r"^(?:cancel\s+(?:the\s+)?shutdown)$", re.I), "cancel_shutdown"),
    (re.compile(r"^(?:בטל\s+(?:את\s+)?(?:ה)?כיבוי)$"), "cancel_shutdown"),
    (re.compile(r"^(?:please\s+)?(?:open|launch|start|run)\s+([\w .+'\-]{2,40})$", re.I), "open"),
    (re.compile(r"^(?:פתח|תפתח|הפעל|תפעיל)\s+(?:את\s+)?(?:ה)?([֐-׿\w .+'\-]{2,40})$"), "open"),
]

_COMPOUND = re.compile(r"(?i)(\band\b|\bthen\b|,|;| ואז | וגם |\bו(?:ת|ה|ש)[֐-׿]+)")
_URL_LIKE = re.compile(r"^[\w\-]+(\.[\w\-]+)+(/\S*)?$")


def match_quick(text: str) -> Optional[tuple[str, dict]]:
    """Return (action_name, args) for a simple command, else None."""
    t = re.sub(r"[.!?]+$", "", text.strip())
    if not t or len(t) > 60:
        return None
    for pat, intent in _P:
        m = pat.match(t)
        if not m:
            continue
        if intent == "set_volume":
            level = int(m.group(1))
            return ("set_volume", {"level": level}) if 0 <= level <= 100 else None
        if intent == "mute":
            return "set_mute", {"mute": True}
        if intent == "unmute":
            return "set_mute", {"mute": False}
        if intent == "lock":
            return "lock_computer", {}
        if intent == "screenshot":
            return "take_screenshot", {}
        if intent in ("next", "previous", "play_pause"):
            return "media_control", {"command": intent}
        if intent == "cancel_shutdown":
            return "cancel_shutdown", {}
        if intent == "open":
            target = m.group(1).strip()
            if _COMPOUND.search(" " + target + " "):
                return None
            if _URL_LIKE.match(target):
                return "open_website", {"url": target}
            return "launch_app", {"name": target}
    return None


CLAIM_PATTERNS = re.compile(
    r"(?i)\b(i(?:'ve| have)\s+(?:opened|launched|closed|set|changed|deleted|moved|created|started|clicked|typed|"
    r"locked|muted|turned)|done[.!]|successfully)|(?:פתחתי|הפעלתי|סגרתי|שיניתי|הגדרתי|מחקתי|העברתי|יצרתי|לחצתי|הקלדתי|נעלתי|השתקתי|בוצע)"
)


def claims_action(text: str) -> bool:
    return bool(CLAIM_PATTERNS.search(text or ""))
