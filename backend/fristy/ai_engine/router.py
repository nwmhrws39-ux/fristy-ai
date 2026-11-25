"""Picks the tool categories relevant to a request.

Small local models choose tools far more reliably from ~10 options than from 55,
so for local providers FRISTY only offers the categories the request is about
(plus a small core set). Cloud models get the full catalog.
"""
from __future__ import annotations

import re

CATEGORY_KEYWORDS: dict[str, str] = {
    "apps": r"open|launch|start|run|app|program|game|play|steam|epic|website|site|browser|url|youtube|google|search|"
            r"פתח|תפתח|הפעל|תפעיל|הרץ|אפליקצי|תוכנ|משחק|תשחק|אתר|דפדפן|גוגל|יוטיוב|חפש באינטרנט|חפש בגוגל|\.com|\.co\.il",
    "windows": r"window|switch|minimi|maximi|close|focus|bring|alt.?tab|חלון|חלונות|עבור ל|תעבור|מזער|תמזער|הגדל|תגדיל|סגור|תסגור|הקטן",
    "audio": r"volume|mute|unmute|sound|audio|music|song|track|media|pause|resume|next|previous|louder|quieter|"
             r"ווליום|עוצמ|קול|שקט|השתק|מוזיקה|שיר|נגן|עצור|הבא|הקודם|תגביר|הגבר|תנמיך|הנמך|רמקול",
    "system": r"system|cpu|ram|memory|gpu|disk|battery|temperature|performance|spec|מעבד|זיכרון|כרטיס מסך|דיסק|סוללה|"
              r"טמפרטור|ביצועים|מפרט|מצב המחשב|כמה מקום",
    "power": r"lock|shutdown|shut down|restart|reboot|turn off|sleep|נעל|תנעל|כבה|תכבה|כיבוי|הפעל מחדש|אתחל|ריסטארט",
    "files": r"file|folder|director|document|download|desktop|pdf|docx|txt|rename|copy|move|delete|organi|duplicate|large|"
             r"קובץ|קבצים|תיקי|מסמך|הורדות|שולחן העבודה|שנה שם|העתק|העבר|מחק|סדר|כפולים|גדולים|סכם",
    "screen": r"screen|screenshot|see|look|what.?s on|click|button|explain this|error message|מסך|צילום מסך|תראה|"
              r"מה רואים|מה מופיע|לחץ|תלחץ|כפתור|הודעת שגיאה|מה כתוב",
    "input": r"click|type|write into|press|key|scroll|mouse|keyboard|הקלד|תקליד|כתוב ב|לחץ|תלחץ|מקש|גלול|תגלול|עכבר|מקלדת",
    "coding": r"code|vscode|vs code|project|script|terminal|command|npm|pip|git|python|readme|bug|compile|"
              r"קוד|פרויקט|סקריפט|טרמינל|פקודה|באג|תכנות",
    "memory": r"remember|forget|my name|prefer|favorite|תזכור|זכור|תשכח|שכח|קוראים לי|אני מעדיף|האהוב",
    "automation": r"mode|routine|automation|custom command|מצב|שגרה|אוטומצי|פקודה מותאמת",
    "integrations": r"fristy|launcher|cleaner|pc manager|playtime|פריסטי|לאונצ'ר|ניקוי|זמן משחק",
}
CORE = {"system", "memory", "automation"}
_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in CATEGORY_KEYWORDS.items()}


def relevant_categories(text: str) -> set[str]:
    cats = {k for k, pat in _COMPILED.items() if pat.search(text or "")}
    if "screen" in cats:
        cats.add("input")  # seeing the screen usually leads to clicking/typing
    if "input" in cats:
        cats.add("screen")
    if not cats:
        cats = {"apps", "windows", "audio"}  # most common requests
    return cats | CORE
