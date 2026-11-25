"""Fast, offline intent matching for very common one-shot commands (English + Hebrew).

Deliberately conservative: patterns must match the WHOLE utterance, so anything
compound or ambiguous goes to the AI model instead.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus
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


_P_EXTRA = [
    (re.compile(r"^(?:please\s+)?(?:turn\s+(?:the\s+)?volume\s+up|volume\s+up|louder|make\s+it\s+louder)(?:\s+by\s+(\d{1,3}))?(?:\s*%)?$", re.I), "vol_up"),
    (re.compile(r"^(?:תגביר|הגבר|תעלה|העלה)\s*(?:את\s+)?(?:ה)?(?:ווליום|קול|עוצמה|סאונד)?(?:\s+ב-?\s*(\d{1,3})\s*%?)?$"), "vol_up"),
    (re.compile(r"^(?:please\s+)?(?:turn\s+(?:the\s+)?volume\s+down|volume\s+down|quieter|make\s+it\s+quieter)(?:\s+by\s+(\d{1,3}))?(?:\s*%)?$", re.I), "vol_down"),
    (re.compile(r"^(?:תנמיך|הנמך|תחליש|החלש|תוריד|הורד)\s*(?:את\s+)?(?:ה)?(?:ווליום|קול|עוצמה|סאונד)?(?:\s+ב-?\s*(\d{1,3})\s*%?)?$"), "vol_down"),
    (re.compile(r"^(?:please\s+)?force\s+(?:close|quit|kill)\s+([\w .+'\-]{2,80})$", re.I), "force_close"),
    (re.compile(r"^(?:סגור|תסגור)\s+בכוח\s+(?:את\s+)?(?:ה)?([\u0590-\u05FF\w .+'\-]{2,80})$"), "force_close"),
    (re.compile(r"^(?:please\s+)?close\s+([\w .+'\-]{2,80})$", re.I), "close"),
    (re.compile(r"^(?:סגור|תסגור)\s+(?:את\s+)?(?:ה)?([֐-׿\w .+'\-]{2,80})$"), "close"),
    (re.compile(r"^(?:please\s+)?(?:switch|go)\s+to\s+([\w .+'\-]{2,80})$", re.I), "switch"),
    (re.compile(r"^(?:עבור|תעבור)\s+ל-?\s*([֐-׿\w .+'\-]{2,80})$"), "switch"),
    (re.compile(r"^(?:please\s+)?minimi[sz]e\s+([\w .+'\-]{2,80})$", re.I), "minimize"),
    (re.compile(r"^(?:מזער|תמזער)\s+(?:את\s+)?(?:ה)?([֐-׿\w .+'\-]{2,80})$"), "minimize"),
    (re.compile(r"^(?:please\s+)?maximi[sz]e\s+([\w .+'\-]{2,80})$", re.I), "maximize"),
    (re.compile(r"^(?:הגדל|תגדיל)\s+(?:את\s+)?(?:ה)?([֐-׿\w .+'\-]{2,80})$"), "maximize"),
    (re.compile(r"^(?:search\s+(?:google\s+)?for|google)\s+(.{2,80})$", re.I), "google"),
    (re.compile(r"^(?:חפש|תחפש)\s+(?:ב)?גוגל\s+(.{2,80})$"), "google"),
    (re.compile(r"^(?:search\s+youtube\s+for|youtube)\s+(.{2,80})$", re.I), "youtube"),
    (re.compile(r"^(?:חפש|תחפש)\s+(?:ב)?יוטיוב\s+(.{2,80})$"), "youtube"),
    (re.compile(r"^(?:system\s+info(?:rmation)?|how\s+is\s+my\s+(?:pc|computer)\s+doing|pc\s+status)$", re.I), "sysinfo"),
    (re.compile(r"^(?:מה\s+)?(?:מצב|נתוני|מפרט)\s+(?:ה)?מחשב$"), "sysinfo"),
    (re.compile(r"^(?:please\s+)?(?:shut\s*down|turn\s+off)\s+(?:the\s+|my\s+)?(?:computer|pc)$", re.I), "shutdown"),
    (re.compile(r"^(?:כבה|תכבה)\s+(?:את\s+)?(?:ה)?מחשב$"), "shutdown"),
    (re.compile(r"^(?:please\s+)?(?:restart|reboot)\s+(?:the\s+|my\s+)?(?:computer|pc)$", re.I), "restart"),
    (re.compile(r"^(?:הפעל|תפעיל)\s+(?:את\s+)?(?:ה)?מחשב\s+מחדש$|^(?:אתחל|תאתחל)\s+(?:את\s+)?(?:ה)?מחשב$"), "restart"),
]

PROCESS_NAMES = {
    "discord": "discord.exe", "chrome": "chrome.exe", "google chrome": "chrome.exe", "microsoft edge": "msedge.exe",
    "edge": "msedge.exe", "firefox": "firefox.exe", "spotify": "spotify.exe", "steam": "steam.exe",
    "notepad": "notepad.exe", "calculator": "calculatorapp.exe", "visual studio code": "code.exe",
    "whatsapp": "whatsapp.exe", "telegram": "telegram.exe", "word": "winword.exe", "excel": "excel.exe",
    "powerpoint": "powerpnt.exe", "teams": "ms-teams.exe", "zoom": "zoom.exe", "vlc": "vlc.exe", "obs": "obs64.exe",
}


def _clean_target(raw: str) -> str:
    from ..computer_control.platform.base import APP_ALIASES, clean_app_query

    t = clean_app_query(re.sub(r"\s+", " ", raw.strip().lower()))
    return APP_ALIASES.get(t, t)

_COMPOUND = re.compile(r"(?i)(\band\b|\bthen\b|,|;| ואז | וגם |\bו(?:ת|ה|ש)[֐-׿]+)")
_URL_LIKE = re.compile(r"^[\w\-]+(\.[\w\-]+)+(/\S*)?$")


def match_quick(text: str) -> Optional[tuple[str, dict]]:
    """Return (action_name, args) for a simple command, else None."""
    t = re.sub(r"[.!?]+$", "", text.strip())
    if not t or len(t) > 100:
        return None
    for pat, intent in _P_EXTRA:
        m = pat.match(t)
        if not m:
            continue
        arg = (m.group(1) or "").strip() if m.groups() else ""
        if intent in ("vol_up", "vol_down"):
            step = int(arg) if arg.isdigit() and 0 < int(arg) <= 100 else 10
            return "change_volume", {"delta": step if intent == "vol_up" else -step}
        if intent in ("close", "force_close", "switch", "minimize", "maximize"):
            if _COMPOUND.search(" " + arg + " "):
                return None
            target = _clean_target(arg)
            if intent in ("close", "force_close"):
                # The action resolves the real running process (e.g. "epic games" -> EpicGamesLauncher.exe).
                args = {"process": PROCESS_NAMES.get(target, target)}
                if intent == "force_close":
                    args["force"] = True
                return "close_app", args
            name = {"switch": "switch_window", "minimize": "minimize_window", "maximize": "maximize_window"}[intent]
            return name, {"query": target}
        if intent == "google":
            return "open_website", {"url": "https://www.google.com/search?q=" + quote_plus(arg)}
        if intent == "youtube":
            return "open_website", {"url": "https://www.youtube.com/results?search_query=" + quote_plus(arg)}
        if intent == "sysinfo":
            return "system_info", {}
        if intent == "shutdown":
            return "shutdown_computer", {"delay_seconds": 60}
        if intent == "restart":
            return "restart_computer", {"delay_seconds": 60}
    if len(t) > 60:
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
