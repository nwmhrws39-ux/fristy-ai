import pytest

from fristy.ai_engine.quick import match_quick
from fristy.computer_control.platform.base import find_running

EPIC_EXE = r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"
PROCS = [
    {"name": "EpicGamesLauncher.exe", "pid": 10, "exe": EPIC_EXE, "title": ""},  # running in the tray
    {"name": "EpicWebHelper.exe", "pid": 11, "exe": r"C:\Program Files (x86)\Epic Games\Launcher\Engine\EpicWebHelper.exe", "title": ""},
    {"name": "Discord.exe", "pid": 20, "exe": r"C:\Users\me\AppData\Local\Discord\app-1.0\Discord.exe", "title": "#general - Discord"},
    {"name": "chrome.exe", "pid": 30, "exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe", "title": "YouTube - Google Chrome"},
    {"name": "chrome.exe", "pid": 31, "exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe", "title": ""},
    {"name": "explorer.exe", "pid": 40, "exe": r"C:\Windows\explorer.exe", "title": "Downloads"},
    {"name": "svchost.exe", "pid": 41, "exe": r"C:\Windows\System32\svchost.exe", "title": ""},
]


@pytest.mark.parametrize("query", ["epicgames", "epic games", "Epic Games Launcher", "EpicGamesLauncher.exe", "אפיק גיימס"])
def test_epic_variants(query):
    assert find_running(query, PROCS)[0]["name"] == "EpicGamesLauncher.exe"


def test_by_window_title_and_grouping():
    g = find_running("youtube", PROCS)[0]
    assert g["name"] == "chrome.exe"
    g = find_running("chrome", PROCS)[0]
    assert g["name"] == "chrome.exe" and sorted(g["pids"]) == [30, 31]
    assert find_running("discord", PROCS)[0]["name"] == "Discord.exe"


def test_system_processes_never_matched():
    assert find_running("explorer", PROCS) == []
    assert find_running("svchost", PROCS) == []


def test_quick_close_keeps_spoken_name():
    assert match_quick("CLOSE EPICGAMES") == ("close_app", {"process": "epic games"})
    assert match_quick("סגור את אפיק גיימס") == ("close_app", {"process": "epic games"})
    assert match_quick("force close epic games") == ("close_app", {"process": "epic games", "force": True})
    assert match_quick("סגור בכוח את דיסקורד") == ("close_app", {"process": "discord.exe", "force": True})


async def test_close_epic_end_to_end(svc, approve_all):
    svc.platform.running = {"epicgameslauncher.exe", "notepad.exe"}
    svc.platform.exe_paths["epicgameslauncher.exe"] = EPIC_EXE
    svc.settings.update({"closable_apps": ["*"]})
    res = await svc.engine.execute("close_app", {"process": "epicgames"})
    assert res.ok and res.data["process"] == "epicgameslauncher.exe"
    assert approve_all.asked[0]["details"]["preview"]["will_close"] == "epicgameslauncher.exe"
    assert "epicgameslauncher.exe" not in svc.platform.running


async def test_close_not_running(svc, approve_all):
    svc.settings.update({"closable_apps": ["*"]})
    res = await svc.engine.execute("close_app", {"process": "photoshop"})
    assert res.ok and "not running" in res.message


async def test_stubborn_app_needs_force(svc, approve_all):
    svc.platform.running.add("epicgameslauncher.exe")
    svc.platform.stubborn.add("epicgameslauncher.exe")
    svc.settings.update({"closable_apps": ["*"]})
    res = await svc.engine.execute("close_app", {"process": "epic games"})
    assert not res.ok and res.code == "still_running"
    res = await svc.engine.execute("close_app", {"process": "epic games", "force": True})
    assert res.ok


async def test_ambiguous_asks(svc, approve_all):
    svc.platform.running = {"steam.exe", "steamwebhelper.exe"}
    svc.settings.update({"closable_apps": ["*"]})
    res = await svc.engine.execute("close_app", {"process": "steam web"})
    assert res.ok or res.code == "ambiguous"


async def test_hebrew_close_reply(svc, approve_all):
    import asyncio
    svc.platform.running.add("EpicGamesLauncher.exe")
    svc.settings.update({"closable_apps": ["*"]})
    q = svc.bus.subscribe()
    svc.orchestrator.start("סגור את אפיק גיימס")
    while True:
        ev = await asyncio.wait_for(q.get(), 5)
        if ev["type"] == "chat.done":
            break
    assert ev["text"] == "סגרתי את Epic Games Launcher."


def test_pc_context_lists_open_apps(svc):
    ctx = svc.orchestrator._pc_context()
    assert "Untitled - Notepad [notepad.exe]" in ctx


async def test_launch_and_switch_without_spaces(svc):
    from fristy.computer_control.platform.base import AppEntry, WindowInfo
    svc.platform.apps.append(AppEntry("Epic Games Launcher", r"C:\fake\Epic.lnk", "shortcut", process_hint="EpicGamesLauncher"))
    res = await svc.engine.execute("launch_app", {"name": "epicgames"})
    assert res.ok and ("launch", "Epic Games Launcher") in svc.platform.calls
    epic_handles = {w.handle for w in svc.platform.windows if "Epic" in w.title}
    res = await svc.engine.execute("switch_window", {"query": "epicgames"})
    focused = [c[1] for c in svc.platform.calls if c[0] == "focus"]
    assert res.ok and focused and focused[-1] in epic_handles
    svc.platform.windows.append(WindowInfo(78, "Downloads", "explorer.exe", 778))
    res = await svc.engine.execute("switch_window", {"query": "explorer"})
    assert res.ok and ("focus", 78) in svc.platform.calls  # windows may target explorer, closing may not
