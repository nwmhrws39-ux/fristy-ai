"""Curated local models (Ollama tags) and RAM-based recommendations."""
from __future__ import annotations

from typing import Any

import psutil

# size_gb = download size; min_ram_gb = practical minimum system RAM to run it.
CURATED: list[dict[str, Any]] = [
    {"id": "qwen2.5:7b", "name": "Qwen 2.5 7B", "size_gb": 4.7, "min_ram_gb": 12, "tools": True, "vision": False,
     "role": "main", "hebrew": 2,
     "en": "Best all-round assistant: reliable computer actions, good Hebrew.",
     "he": "העוזר המומלץ: ביצוע פעולות אמין ועברית טובה."},
    {"id": "llama3.2:3b", "name": "Llama 3.2 3B", "size_gb": 2.0, "min_ram_gb": 8, "tools": True, "vision": False,
     "hebrew": 1, "role": "main",
     "en": "Light and fast; for PCs with 8 GB RAM. Weaker Hebrew.",
     "he": "קל ומהיר, למחשבים עם 8GB זיכרון. עברית חלשה יותר."},
    {"id": "qwen2.5:3b", "name": "Qwen 2.5 3B", "size_gb": 1.9, "min_ram_gb": 8, "tools": True, "vision": False,
     "hebrew": 1, "role": "main",
     "en": "Light model with decent Hebrew and tool use.",
     "he": "מודל קל עם עברית סבירה ותמיכה בפעולות."},
    {"id": "qwen2.5:1.5b", "name": "Qwen 2.5 1.5B", "size_gb": 1.0, "min_ram_gb": 4, "tools": True, "vision": False,
     "hebrew": 1, "role": "main",
     "en": "Smallest option for weak PCs; simple tasks only.",
     "he": "האפשרות הקטנה ביותר למחשבים חלשים; משימות פשוטות בלבד."},
    {"id": "qwen3:8b", "name": "Qwen 3 8B", "size_gb": 5.2, "min_ram_gb": 16, "tools": True, "vision": False,
     "hebrew": 2, "role": "main",
     "en": "Stronger reasoning for multi-step agent tasks; slower.",
     "he": "חשיבה חזקה יותר למשימות סוכן מרובות שלבים; איטי יותר."},
    {"id": "gemma3:12b", "name": "Gemma 3 12B", "size_gb": 8.1, "min_ram_gb": 16, "tools": False, "vision": True,
     "hebrew": 3, "role": "main",
     "en": "Best local Hebrew + can see the screen. Actions work through FRISTY's text protocol (less reliable than Qwen).",
     "he": "העברית הטובה ביותר מקומית, ורואה את המסך. פעולות עובדות דרך פרוטוקול טקסט (פחות אמין מ-Qwen)."},
    {"id": "aya-expanse:8b", "name": "Aya Expanse 8B", "size_gb": 5.1, "min_ram_gb": 12, "tools": False, "vision": False,
     "hebrew": 3, "role": "main",
     "en": "Multilingual model with strong Hebrew; best for conversation and writing.",
     "he": "מודל רב-לשוני עם עברית חזקה; מצוין לשיחה ולכתיבה."},
    {"id": "gemma3:4b", "name": "Gemma 3 4B (vision)", "size_gb": 3.3, "min_ram_gb": 8, "tools": False, "vision": True,
     "hebrew": 2, "role": "vision",
     "en": "Can see screenshots: use it for “explain my screen”.",
     "he": "רואה צילומי מסך: מתאים ל״הסבר מה על המסך״."},
    {"id": "qwen2.5vl:7b", "name": "Qwen 2.5 VL 7B (vision)", "size_gb": 6.0, "min_ram_gb": 16, "tools": False,
     "vision": True, "hebrew": 1, "role": "vision",
     "en": "Stronger screen understanding; needs 16 GB RAM.",
     "he": "הבנת מסך חזקה יותר; דורש 16GB זיכרון."},
]


def total_ram_gb() -> float:
    return round(psutil.virtual_memory().total / 1e9, 1)


def recommend(ram_gb: float | None = None) -> dict[str, Any]:
    ram = total_ram_gb() if ram_gb is None else ram_gb
    if ram >= 15:
        main = "qwen2.5:7b"
    elif ram >= 7:
        main = "qwen2.5:3b"
    else:
        main = "qwen2.5:1.5b"
    vision = "gemma3:4b" if ram >= 7 else None
    models = []
    for m in CURATED:
        models.append({**m, "fits": ram >= m["min_ram_gb"], "recommended": m["id"] in (main, vision)})
    return {"ram_gb": ram, "main": main, "vision": vision, "models": models}
