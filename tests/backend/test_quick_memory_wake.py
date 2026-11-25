import numpy as np
import pytest

from fristy.ai_engine.quick import claims_action, match_quick
from fristy.ai_engine.types import parse_text_tool_calls, simplify_schema
from fristy.memory.store import extract_learnable
from fristy.voice_engine.audio import float32_to_wav, wav_to_float32
from fristy.voice_engine.wake import detect_wake


@pytest.mark.parametrize("text,expected", [
    ("set volume to 30", ("set_volume", {"level": 30})),
    ("Volume 45%", ("set_volume", {"level": 45})),
    ("הגדר עוצמה ל-30", ("set_volume", {"level": 30})),
    ("ווליום 20", ("set_volume", {"level": 20})),
    ("mute", ("set_mute", {"mute": True})),
    ("השתק", ("set_mute", {"mute": True})),
    ("lock the computer", ("lock_computer", {})),
    ("נעל את המחשב", ("lock_computer", {})),
    ("next song", ("media_control", {"command": "next"})),
    ("שיר הבא", ("media_control", {"command": "next"})),
    ("open discord", ("launch_app", {"name": "discord"})),
    ("פתח את דיסקורד", ("launch_app", {"name": "דיסקורד"})),
    ("open youtube.com", ("open_website", {"url": "youtube.com"})),
    ("take a screenshot", ("take_screenshot", {})),
])
def test_quick_intents(text, expected):
    assert match_quick(text) == expected


@pytest.mark.parametrize("text", ["open discord and launch gta", "open discord, then spotify",
                                  "what is the volume of a sphere", "set volume to 300", "פתח דיסקורד ותפעיל משחק",
                                  "how do I open a file in python?"])
def test_quick_rejects_complex(text):
    assert match_quick(text) is None


def test_claims_action():
    assert claims_action("I've opened Discord for you.")
    assert claims_action("פתחתי את דיסקורד")
    assert not claims_action("Discord is a chat app.")


def test_learnable():
    assert extract_learnable("My favorite game is Valorant.") == [("favorite_game", "favorite game", "Valorant")]
    assert extract_learnable("call me Noa")[0][2] == "Noa"
    assert extract_learnable("what's the weather") == []


def test_memory_export_import(svc):
    svc.memory.upsert("project", "main project", "FRISTY AI")
    data = svc.memory.export()
    svc.memory.clear()
    assert svc.memory.list() == []
    assert svc.memory.import_(data) == 1
    assert "FRISTY AI" in svc.memory.context_block()


def test_memory_disabled(svc):
    svc.settings.update({"memory": {"enabled": False}})
    from fristy.computer_control.base import ActionError
    with pytest.raises(ActionError):
        svc.memory.upsert("fact", "a", "b")
    assert svc.memory.context_block() == ""


@pytest.mark.parametrize("text,detected,rest", [
    ("Hey Fristy, open Discord.", True, "open discord"),
    ("hey frosty what time is it", True, "what time is it"),
    ("היי פריסטי תפתח את כרום", True, "תפתח את כרום"),
    ("Fristy", True, ""),
    ("I went to the store today", False, ""),
    ("the party was fun", False, ""),
])
def test_wake(text, detected, rest):
    d, r = detect_wake(text, ["hey fristy", "היי פריסטי"])
    assert d == detected
    if detected:
        assert r == rest


def test_wav_roundtrip_and_resample():
    sig = np.sin(np.linspace(0, 100, 48000)).astype(np.float32) * 0.5
    wav = float32_to_wav(sig, sr=48000)
    out = wav_to_float32(wav)
    assert abs(len(out) - 16000) <= 1 and 0.3 < np.max(out) <= 0.51


def test_text_protocol_parse():
    text, calls = parse_text_tool_calls(
        'Sure.\n<action>{"name": "set_volume", "arguments": {"level": 30}}</action>\n'
        '<action>{"name": "evil_tool", "arguments": {}}</action>', {"set_volume"})
    assert text == "Sure." and len(calls) == 1 and calls[0].arguments == {"level": 30}


def test_simplify_schema_optional_and_literal():
    from pydantic import BaseModel
    from typing import Literal, Optional

    class M(BaseModel):
        a: Optional[str] = None
        b: Literal["x", "y"]
        c: dict[str, str]

    s = simplify_schema(M.model_json_schema(), allow_additional=False)
    assert s["properties"]["a"] == {"type": "string", "nullable": True}
    assert s["properties"]["b"]["enum"] == ["x", "y"]
    assert "title" not in s and "additionalProperties" not in s["properties"]["c"]
