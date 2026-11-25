import pytest

from fristy.computer_control.base import ExecutionContext
from fristy.computer_control.platform.base import match_apps
from conftest import enable


async def test_set_volume_verified(svc):
    res = await svc.engine.execute("set_volume", {"level": 30})
    assert res.ok and res.verified is True and svc.platform.volume == 30


async def test_set_volume_readback_mismatch_is_failure(svc):
    svc.platform.volume_readback_offset = 20
    res = await svc.engine.execute("set_volume", {"level": 30})
    assert not res.ok and res.verified is False


async def test_change_volume_clamps(svc):
    svc.platform.volume = 95
    res = await svc.engine.execute("change_volume", {"delta": 20})
    assert res.ok and svc.platform.volume == 100


async def test_launch_app_fuzzy_and_verified(svc):
    res = await svc.engine.execute("launch_app", {"name": "discord"})
    assert res.ok and ("launch", "Discord") in svc.platform.calls
    assert res.verified is True


async def test_launch_hebrew_alias(svc):
    res = await svc.engine.execute("launch_app", {"name": "דיסקורד"})
    assert res.ok and ("launch", "Discord") in svc.platform.calls


async def test_launch_game_alias(svc):
    res = await svc.engine.execute("launch_game", {"name": "GTA V"})
    assert res.ok and ("launch", "Grand Theft Auto V") in svc.platform.calls


async def test_launch_unknown_app(svc):
    res = await svc.engine.execute("launch_app", {"name": "Photoshoppp Ultra 3000"})
    assert not res.ok and res.code == "not_found"


def test_match_prefers_app_over_uninstaller(platform):
    best = match_apps("discord", platform.apps)[0][1]
    assert best.name == "Discord"


async def test_open_website_validates_scheme(svc):
    res = await svc.engine.execute("open_website", {"url": "javascript:alert(1)"})
    assert res.code == "invalid_arguments"
    res = await svc.engine.execute("open_website", {"url": "youtube.com"})
    assert res.ok and ("open_uri", "https://youtube.com") in svc.platform.calls
    res = await svc.engine.execute("open_website", {"url": "file:///C:/Windows/System32/cmd.exe"})
    assert not res.ok


async def test_window_actions(svc):
    assert (await svc.engine.execute("switch_window", {"query": "notepad"})).ok
    assert ("focus", 1) in svc.platform.calls
    assert (await svc.engine.execute("minimize_window", {"query": "Discord"})).ok
    res = await svc.engine.execute("maximize_window", {"query": "nonexistent window xyz"})
    assert res.code == "not_found"


async def test_close_app_requires_approved_list_and_confirmation(svc, approve_all):
    svc.platform.running.add("discord.exe")
    res = await svc.engine.execute("close_app", {"process": "discord"})
    assert res.code == "not_approved_app"
    svc.settings.update({"closable_apps": ["notepad.exe", "discord.exe"]})
    res = await svc.engine.execute("close_app", {"process": "Discord"})
    assert res.ok and res.verified
    assert approve_all.asked and approve_all.asked[0]["risk"] == "high"


async def test_media_and_mute(svc):
    assert (await svc.engine.execute("media_control", {"command": "next"})).ok
    assert ("media", "next") in svc.platform.calls
    res = await svc.engine.execute("set_mute", {"mute": True})
    assert res.ok and res.verified


async def test_lock_is_medium_and_confirmed_for_agent(svc, approve_all):
    enable(svc, "power_management")
    assert (await svc.engine.execute("lock_computer", {}, ExecutionContext(source="ui"))).ok
    assert approve_all.asked == []
    await svc.engine.execute("lock_computer", {}, ExecutionContext(source="agent"))
    assert len(approve_all.asked) == 1


async def test_input_blocked_without_permission(svc):
    res = await svc.engine.execute("click_at", {"x": 10, "y": 10})
    assert res.code == "permission_denied"
    res = await svc.engine.execute("type_text", {"text": "hello"})
    assert res.code == "permission_denied"


async def test_screen_capture_blocked_on_secure_desktop(svc, approve_all):
    enable(svc, "screen_view")
    svc.platform.secure = True
    res = await svc.engine.execute("take_screenshot", {})
    assert res.code == "secure_screen"


async def test_screen_capture_blocked_on_password_manager(svc):
    from fristy.computer_control.platform.base import WindowInfo
    enable(svc, "screen_view")
    svc.platform.fg = WindowInfo(5, "Vault", "KeePassXC.exe", 55)
    res = await svc.engine.execute("take_screenshot", {})
    assert res.code == "sensitive_screen"


async def test_analyze_screen_needs_confirmation_for_cloud(svc, approve_all):
    enable(svc, "screen_view")
    svc.settings.update({"ai": {"provider": "openai"}})
    approve_all.decision["value"] = False
    res = await svc.engine.execute("analyze_screen", {})
    assert res.code == "not_approved"
    assert "SEND it to the cloud" in approve_all.asked[0]["summary"]


async def test_system_info_real(svc):
    res = await svc.engine.execute("system_info", {})
    assert res.ok and res.data["cpu_cores_logical"] >= 1 and res.data["ram_total_gb"] > 0


async def test_pc_performance_builtin(svc):
    res = await svc.engine.execute("pc_performance", {})
    assert res.ok and res.data["source"] == "builtin" and "cpu_percent" in res.data


async def test_remember_rejects_password(svc):
    res = await svc.engine.execute("remember", {"category": "fact", "key": "wifi", "value": "password: hunter22"})
    assert not res.ok and res.code == "sensitive_data"
    res = await svc.engine.execute("remember", {"category": "favorite_game", "key": "favorite game",
                                                "value": "Rocket League"})
    assert res.ok and svc.memory.list()[0]["value"] == "Rocket League"
