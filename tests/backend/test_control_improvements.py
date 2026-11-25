import asyncio

import pytest

from fristy.ai_engine.quick import match_quick
from fristy.ai_engine.router import relevant_categories
from fristy.ai_engine.hebrew import reply_language, quick_reply_he
from fristy.computer_control.base import ExecutionContext
from fastapi.testclient import TestClient
from fristy.api.app import create_app


@pytest.mark.parametrize("text,expected", [
    ("תגביר", ("change_volume", {"delta": 10})),
    ("תגביר את הווליום ב-20", ("change_volume", {"delta": 20})),
    ("תנמיך את הקול", ("change_volume", {"delta": -10})),
    ("volume up", ("change_volume", {"delta": 10})),
    ("quieter", ("change_volume", {"delta": -10})),
    ("סגור את דיסקורד", ("close_app", {"process": "discord.exe"})),
    ("close chrome", ("close_app", {"process": "chrome.exe"})),
    ("עבור לכרום", ("switch_window", {"query": "chrome"})),
    ("switch to notepad", ("switch_window", {"query": "notepad"})),
    ("מזער את ספוטיפיי", ("minimize_window", {"query": "spotify"})),
    ("חפש בגוגל מזג אוויר בתל אביב", ("open_website", {"url": "https://www.google.com/search?q=%D7%9E%D7%96%D7%92+%D7%90%D7%95%D7%95%D7%99%D7%A8+%D7%91%D7%AA%D7%9C+%D7%90%D7%91%D7%99%D7%91"})),
    ("מה מצב המחשב", ("system_info", {})),
    ("תכבה את המחשב", ("shutdown_computer", {"delay_seconds": 60})),
    ("restart the computer", ("restart_computer", {"delay_seconds": 60})),
])
def test_new_quick_intents(text, expected):
    assert match_quick(text) == expected


def test_quick_close_rejects_compound():
    assert match_quick("סגור את דיסקורד ותפתח כרום") is None


def test_router():
    assert {"audio"} <= relevant_categories("תגביר את המוזיקה")
    assert {"files"} <= relevant_categories("find my resume file")
    assert {"screen", "input"} <= relevant_categories("מה מופיע לי על המסך?")
    cats = relevant_categories("hello there")
    assert {"apps", "windows", "audio", "system", "memory"} <= cats and "files" not in cats


def test_local_models_get_fewer_tools(svc):
    from conftest import enable
    enable(svc, "file_access", "screen_view", "mouse_control", "keyboard_control", "power_management", "terminal_exec")
    local = [t.name for t in svc.orchestrator.tools("set the volume to 30")]
    assert "set_volume" in local and "delete_file" not in local and len(local) < 25
    svc.settings.update({"ai": {"provider": "anthropic"}})
    cloud = [t.name for t in svc.orchestrator.tools("set the volume to 30")]
    assert "delete_file" in cloud and len(cloud) > len(local)


def test_reply_language():
    assert reply_language("פתח את כרום", "en") == "he"
    assert reply_language("open chrome", "he") == "en"
    assert reply_language("30%", "he") == "he"


def test_hebrew_quick_replies():
    assert quick_reply_he("set_volume", {"level": 30}, True, "Volume set to 30%.", {"level": 30}) == "עוצמת הקול הוגדרה ל-30%."
    assert quick_reply_he("set_volume", {"level": 30}, False, "Permission 'system_control' is disabled.", {}).startswith("לא ביצעתי")


async def test_hebrew_quick_end_to_end(svc):
    q = svc.bus.subscribe()
    svc.orchestrator.start("תגביר את הווליום ב-20")
    while True:
        ev = await asyncio.wait_for(q.get(), 5)
        if ev["type"] == "chat.done":
            break
    assert svc.platform.volume == 70 and ev["text"] == "עוצמת הקול עכשיו 70%."


async def test_relaxed_confirmations(svc, approve_all):
    from conftest import enable
    enable(svc, "power_management", "file_access")
    svc.settings.update({"confirmation_level": "relaxed"})
    # medium risk from the agent: no confirmation in relaxed mode
    assert (await svc.engine.execute("lock_computer", {}, ExecutionContext(source="agent"))).ok
    assert approve_all.asked == []
    # high risk still asks
    await svc.engine.execute("shutdown_computer", {"delay_seconds": 30}, ExecutionContext(source="chat"))
    assert [a["action"] for a in approve_all.asked] == ["shutdown_computer"]
    # untrusted content still escalates medium actions
    await svc.engine.execute("lock_computer", {}, ExecutionContext(source="chat", untrusted_seen=True))
    assert len(approve_all.asked) == 2


def test_full_access_endpoint(svc):
    from pathlib import Path
    app = create_app(svc.config, svc)
    H = {"Authorization": "Bearer test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        s = c.post("/api/full-access", headers=H, json={"enable": True}).json()
        assert all(s["permissions"].values()) and s["confirmation_level"] == "relaxed" and s["full_access"]
        assert str(Path.home()) in s["approved_dirs"] and "*" in s["closable_apps"]
        s = c.post("/api/full-access", headers=H, json={"enable": False}).json()
        assert not s["permissions"]["terminal_exec"] and s["confirmation_level"] == "strict" and "*" not in s["closable_apps"]


async def test_close_any_app_with_full_access(svc, approve_all):
    svc.platform.running.add("spotify.exe")
    svc.settings.update({"closable_apps": ["*"]})
    res = await svc.engine.execute("close_app", {"process": "spotify"})
    assert res.ok and approve_all.asked  # still confirmed (high risk)
