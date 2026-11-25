import json

import httpx
import pytest

from fristy.computer_control.platform.game_libraries import epic_games, parse_acf, parse_vdf_paths, steam_games

VDF = r'''"libraryfolders"
{
    "0"
    {
        "path"		"C:\\Program Files (x86)\\Steam"
        "apps" { "228980" "1" }
    }
    "1"
    {
        "path"		"D:\\SteamLibrary"
    }
}'''


def test_vdf_paths():
    assert parse_vdf_paths(VDF) == [r"C:\Program Files (x86)\Steam", r"D:\SteamLibrary"]


def test_steam_and_epic(tmp_path):
    apps = tmp_path / "steam" / "steamapps"
    apps.mkdir(parents=True)
    (apps / "appmanifest_271590.acf").write_text('"AppState"\n{\n"appid" "271590"\n"name" "Grand Theft Auto V"\n"installdir" "GTAV"\n}')
    (apps / "appmanifest_228980.acf").write_text('"AppState"\n{\n"appid" "228980"\n"name" "Steamworks Common Redistributables"\n}')
    games = steam_games(tmp_path / "steam")
    assert [(g.name, g.target) for g in games] == [("Grand Theft Auto V", "steam://rungameid/271590")]
    man = tmp_path / "epic"
    man.mkdir()
    (man / "a.item").write_text(json.dumps({"DisplayName": "Fortnite", "AppName": "Fortnite",
                                            "LaunchExecutable": "FortniteGame/Binaries/Win64/FortniteLauncher.exe",
                                            "AppCategories": ["public", "games"]}))
    eg = epic_games(man)
    assert eg[0].name == "Fortnite" and "com.epicgames.launcher://apps/Fortnite" in eg[0].target


async def test_launcher_integration(svc, monkeypatch):
    svc.settings.update({"integrations": {"launcher": {"enabled": True}}})
    svc.secrets.set("integration_launcher_token", "tok")
    real = httpx.AsyncClient

    def handler(req):
        assert req.headers["authorization"] == "Bearer tok"
        if req.url.path == "/api/v1/games":
            return httpx.Response(200, json=[{"id": "g1", "name": "Valorant", "playtime_minutes": 600}])
        if req.url.path == "/api/v1/games/g1/launch":
            return httpx.Response(200, json={"ok": True, "running": True})
        if req.url.path == "/api/v1/status":
            return httpx.Response(200, json={"app": "fristy-launcher", "version": "1.0"})
        return httpx.Response(404)

    class P(real):
        def __init__(self, *a, **kw):
            kw.pop("trust_env", None)
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)
    monkeypatch.setattr(httpx, "AsyncClient", P)
    res = await svc.engine.execute("fristy_launcher_launch", {"game": "Valorant"})
    assert res.ok and res.verified is True
    res = await svc.engine.execute("fristy_launcher_playtime", {"query": ""})
    assert res.data["playtime"][0]["hours"] == 10.0
    st = await svc.integrations["launcher"].check()
    assert st["connected"]


async def test_integration_disabled_and_nonlocal(svc):
    res = await svc.engine.execute("fristy_launcher_games", {"query": ""})
    assert res.code == "integration_disabled"
    svc.settings.update({"integrations": {"launcher": {"enabled": True, "base_url": "http://192.168.1.5:47801"}}})
    svc.secrets.set("integration_launcher_token", "tok")
    res = await svc.engine.execute("fristy_launcher_games", {"query": ""})
    assert res.code == "integration_not_local"
