"""Hebrew language support: detection, prompt directive, localized system texts."""
from __future__ import annotations

import re
from typing import Any

_HE = re.compile(r"[֐-׿]")
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def is_hebrew(text: str) -> bool:
    return bool(_HE.search(text or ""))


def reply_language(text: str, ui_language: str) -> str:
    """'he' if the user wrote Hebrew, or the UI is Hebrew and the message has no English words."""
    if is_hebrew(text):
        return "he"
    if ui_language == "he" and not _LATIN_WORD.search(text or ""):
        return "he"
    return "en"


# Written in Hebrew on purpose: models follow a same-language instruction far more reliably.
HEBREW_DIRECTIVE = """
הנחיית שפה (חשוב מאוד):
- המשתמש מדבר עברית. ענה תמיד בעברית תקנית, טבעית ושוטפת, כמו דובר עברית ילידי.
- אל תערבב אנגלית בתוך המשפטים. מותר להשאיר באנגלית רק שמות של תוכנות, קבצים, פקודות וקוד.
- השתמש בלשון פנייה ישירה וקצרה ("פתחתי", "הגדרתי", "לא הצלחתי כי…"), בלי תרגום מילולי מאנגלית.
- מספרים, אחוזים ושעות כתוב בספרות (30%, 14:30).
- תוצאות הכלים מגיעות באנגלית - תרגם את המשמעות שלהן לעברית בתשובה שלך, ודווח בכנות על הצלחה או כישלון.
"""

TOOL_RESULT_SUFFIX_HE = " (ענה למשתמש בעברית.)"

TEXT: dict[str, dict[str, str]] = {
    "stopped": {"en": "⏹ Stopped.", "he": "⏹ נעצר."},
    "no_actions_needed": {"en": "No computer actions are needed for that.", "he": "אין צורך בפעולות במחשב בשביל זה."},
    "cannot_plan": {"en": "I can't perform this plan:", "he": "אני לא יכול לבצע את התוכנית הזו:"},
    "plan_cancelled": {"en": "Plan cancelled - nothing was executed.", "he": "התוכנית בוטלה - לא בוצעה שום פעולה."},
    "report": {"en": "**Execution report**", "he": "**דוח ביצוע**"},
    "not_executed": {"en": "Not executed", "he": "לא בוצע"},
    "skipped": {"en": "Skipped", "he": "דולג"},
    "not_verified": {"en": "(not verified)", "he": "(לא אומת)"},
    "no_actions": {"en": "No actions were executed.", "he": "לא בוצעו פעולות."},
}


def t(key: str, lang: str) -> str:
    return TEXT[key].get(lang) or TEXT[key]["en"]


_MEDIA_HE = {"play_pause": "הפעלה/השהיה", "next": "השיר הבא", "previous": "השיר הקודם", "stop": "עצירה"}


def quick_reply_he(name: str, args: dict[str, Any], ok: bool, message: str, data: dict[str, Any]) -> str:
    """Hebrew reply for fast local commands (built from the real result, never assumed)."""
    if not ok:
        if "permission" in message.lower():
            return f"לא ביצעתי: ההרשאה המתאימה כבויה בהגדרות. ({message})"
        if "did not approve" in message.lower():
            return "הפעולה לא בוצעה כי לא אישרת אותה."
        if "matches several running apps" in message:
            return "יש כמה אפליקציות פתוחות שמתאימות לשם הזה: " + message.split(":", 1)[1].replace("Which one?", "").strip() + " - לאיזו התכוונת?"
        if "did not close by itself" in message:
            return f"האפליקציה לא נסגרה מעצמה (אולי היא רצה ברקע או מבקשת לשמור). אמור ״סגור בכוח {args.get('process')}״ כדי לסגור אותה בכל זאת."
        return f"לא הצלחתי: {message}"
    if name == "set_volume":
        return f"עוצמת הקול הוגדרה ל-{data.get('level', args.get('level'))}%."
    if name == "set_mute":
        return "הקול הושתק." if args.get("mute") else "ההשתקה בוטלה."
    if name == "lock_computer":
        return "המחשב ננעל."
    if name == "take_screenshot":
        return f"צילום המסך נשמר: {data.get('path', '')}"
    if name == "media_control":
        return f"בוצע: {_MEDIA_HE.get(args.get('command', ''), args.get('command', ''))}."
    if name == "cancel_shutdown":
        return "הכיבוי המתוזמן בוטל."
    if name == "launch_app":
        app = (data.get("app") or {}).get("name") or args.get("name")
        return f"פתחתי את {app}." if "Launched" in message else f"הפעלתי את {app} (החלון עוד לא הופיע)."
    if name == "open_website":
        return f"פתחתי את {args.get('url')} בדפדפן."
    if name == "change_volume":
        return f"עוצמת הקול עכשיו {data.get('level', '?')}%."
    if name == "close_app":
        if "Closed" in message:
            return f"סגרתי את {data.get('app') or data.get('process') or args.get('process')}."
        return f"{args.get('process')} לא פתוח כרגע."
    if name == "switch_window":
        return f"עברתי לחלון {args.get('query')}."
    if name == "minimize_window":
        return f"מזערתי את {args.get('query')}."
    if name == "maximize_window":
        return f"הגדלתי את {args.get('query')}."
    if name == "system_info":
        disks = ", ".join(f"{d['mount']} {d['free_gb']}GB פנויים" for d in data.get("disks", [])[:3])
        gpu = (data.get("gpus") or [{}])[0].get("name") or "לא זוהה"
        return (f"מעבד: {data.get('cpu')} ({data.get('cpu_cores_logical')} ליבות), עומס {data.get('cpu_percent')}%\n"
                f"זיכרון: {data.get('ram_total_gb')}GB, בשימוש {data.get('ram_used_percent')}%\n"
                f"כרטיס מסך: {gpu}\nדיסקים: {disks}\nמערכת: {data.get('os')}")
    if name in ("shutdown_computer", "restart_computer"):
        what = "כיבוי" if name == "shutdown_computer" else "הפעלה מחדש"
        return f"{what} מתוזמן בעוד {args.get('delay_seconds')} שניות. אמור ״בטל כיבוי״ כדי לבטל."
    return f"בוצע: {message}"


def sysinfo_en(data: dict[str, Any]) -> str:
    disks = ", ".join(f"{d['mount']} {d['free_gb']} GB free" for d in data.get("disks", [])[:3])
    gpu = (data.get("gpus") or [{}])[0].get("name") or "not detected"
    return (f"CPU: {data.get('cpu')} ({data.get('cpu_cores_logical')} threads), load {data.get('cpu_percent')}%\n"
            f"RAM: {data.get('ram_total_gb')} GB, {data.get('ram_used_percent')}% used\n"
            f"GPU: {gpu}\nDisks: {disks}\nOS: {data.get('os')}")
