"""Catalog of every action FRISTY can perform. Each is validated, permission
checked, confirmed when needed, executed, verified and audited by ActionEngine."""
from __future__ import annotations

import asyncio
import difflib
import re
import time
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from ..screen_analysis import cv_utils
from ..security.sanitize import fence_untrusted
from .base import ActionError, ActionResult, ActionSpec, EmptyParams, ExecutionContext, Risk
from .platform.base import match_apps

CLOUD_PROVIDERS = {"openai", "anthropic", "gemini"}


def _t(fn, *a, **kw):
    return asyncio.to_thread(fn, *a, **kw)


# ----------------------------------------------------------------- params
class AppParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Application or game name, e.g. 'Discord'")


class UrlParams(BaseModel):
    url: str = Field(..., max_length=2000, description="http(s) URL or a domain like 'youtube.com'")

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(?!\d+(?:/|$))", v)
        if scheme and scheme.group(1).lower() not in ("http", "https"):
            raise ValueError("only http/https URLs are allowed")
        if not scheme:
            v = "https://" + v
        u = urlparse(v)
        host = u.hostname or ""
        if u.scheme not in ("http", "https") or not host or " " in u.netloc or not re.match(r"^[\w.\-\[\]:]+$", host):
            raise ValueError("only http/https URLs are allowed")
        return v


class WindowParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Window title or application name")


class CloseAppParams(BaseModel):
    process: str = Field(..., min_length=1, max_length=100, description="Process name, e.g. 'discord.exe' or 'Discord'")
    force: bool = Field(False, description="Terminate if the app does not close gracefully")


class VolumeParams(BaseModel):
    level: int = Field(..., ge=0, le=100, description="Master volume percent 0-100")


class VolumeDeltaParams(BaseModel):
    delta: int = Field(..., ge=-100, le=100, description="Change in percent, e.g. -10")


class MuteParams(BaseModel):
    mute: bool = True


class MediaParams(BaseModel):
    command: Literal["play_pause", "next", "previous", "stop"]


class ShutdownParams(BaseModel):
    delay_seconds: int = Field(60, ge=0, le=86400, description="Delay before shutdown")


class PathParams(BaseModel):
    path: str = Field(..., min_length=1, max_length=1000)


class FindParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="File name or glob, e.g. 'report' or '*.pdf'")
    root: Optional[str] = Field(None, description="Approved folder to search (default: all approved folders)")
    limit: int = Field(30, ge=1, le=200)


class ContentSearchParams(BaseModel):
    text: str = Field(..., min_length=2, max_length=200)
    root: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)


class RenameParams(BaseModel):
    path: str
    new_name: str = Field(..., min_length=1, max_length=255)


class CopyMoveParams(BaseModel):
    source: str
    destination: str
    overwrite: bool = False


class LargeFilesParams(BaseModel):
    root: Optional[str] = None
    min_mb: float = Field(100, ge=1, le=100000)


class DuplicateParams(BaseModel):
    root: Optional[str] = None


class WriteTextParams(BaseModel):
    path: str
    content: str = Field(..., max_length=500_000)
    overwrite: bool = False


class ScreenParams(BaseModel):
    question: str = Field("Describe what is on the screen.", max_length=1000)
    monitor: int = Field(1, ge=1, le=8)


class ClickElementParams(BaseModel):
    element_id: Optional[str] = Field(None, description="Element id from list_ui_elements, e.g. 'e12'")
    name: Optional[str] = Field(None, description="Visible name of the element if no id is known")


class ClickAtParams(BaseModel):
    x: int = Field(..., ge=0, le=20000)
    y: int = Field(..., ge=0, le=20000)
    button: Literal["left", "right", "middle"] = "left"
    double: bool = False


class LocateParams(BaseModel):
    description: str = Field(..., min_length=2, max_length=300, description="What to find, e.g. 'the Send button'")


class ScrollParams(BaseModel):
    amount: int = Field(..., ge=-50, le=50, description="Positive scrolls up, negative scrolls down (wheel clicks)")


class TypeParams(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    element_id: Optional[str] = Field(None, description="Optional target edit field id from list_ui_elements")


class KeysParams(BaseModel):
    keys: list[str] = Field(..., min_length=1, max_length=4, description="e.g. ['ctrl','s'] or ['enter']")


class CodeWriteParams(BaseModel):
    path: str
    content: str = Field(..., max_length=500_000)


class StructureParams(BaseModel):
    root: str = Field(..., description="Approved folder in which to create the project")
    files: dict[str, str] = Field(..., description="Relative path -> file content; end a key with '/' for a folder")


class VSCodeParams(BaseModel):
    path: Optional[str] = None


class CommandParams(BaseModel):
    command: str = Field(..., min_length=1, max_length=2000)
    cwd: str = Field(..., description="Approved project folder to run in")
    timeout_seconds: int = Field(300, ge=5, le=1800)


class RememberParams(BaseModel):
    category: Literal["preference", "favorite_game", "frequent_app", "language", "project", "routine", "fact"]
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1, max_length=2000)


class ForgetParams(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)


class CustomCommandParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


# ---------------------------------------------------------------- builder
def build_registry(svc) -> None:
    reg = svc.registry
    plat = svc.platform
    files = svc.files

    def add(name, desc, params, perm, risk, handler, **kw):
        reg.register(ActionSpec(name=name, description=desc, params=params, permission=perm, risk=risk,
                                handler=handler, **kw))

    def ok(msg, verified=None, **data):
        return ActionResult(True, msg, data=data, verified=verified)

    # ---------------------------------------------------------- apps
    def resolve_app(name: str, games_only: bool = False):
        apps = plat.list_apps()
        matches = match_apps(name, apps, games_only=games_only)
        if not matches:
            hint = ", ".join(a.name for _, a in match_apps(name, apps, limit=3, games_only=False)) if not games_only else ""
            raise ActionError(f"No installed {'game' if games_only else 'application'} matches '{name}'."
                              + (f" Did you mean: {hint}?" if hint else ""), "not_found")
        score, app = matches[0]
        if len(matches) > 1 and matches[1][0] == score and score < 1.0:
            names = ", ".join(a.name for _, a in matches[:4])
            raise ActionError(f"'{name}' is ambiguous: {names}. Please be more specific.", "ambiguous")
        return app

    async def _launch(ctx, args, games_only=False):
        app = await _t(resolve_app, args.name, games_only)
        before = {w.pid for w in await _t(plat.list_windows)}
        await _t(plat.launch, app)
        svc.memory.track_usage("game" if app.is_game else "app", app.name)
        verified = None
        token = re.sub(r"[^a-z0-9]", "", (app.process_hint or app.name).lower())[:6]
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                wins = await _t(plat.list_windows)
            except ActionError:
                break
            new = [w for w in wins if w.pid not in before]
            if any(token and (token in re.sub(r"[^a-z0-9]", "", w.title.lower()) or
                              token in re.sub(r"[^a-z0-9]", "", w.process.lower())) for w in wins + new):
                verified = True
                break
        msg = f"Launched {app.name}." if verified else f"Started {app.name} (its window has not appeared yet)."
        return ok(msg, verified=verified, app=app.to_dict())

    async def list_apps(ctx, args):
        apps = await _t(plat.list_apps, True)
        return ok(f"Found {len(apps)} applications and games.", verified=True,
                  apps=[{"name": a.name, "kind": a.kind, "is_game": a.is_game} for a in apps[:400]])

    add("list_apps", "List installed applications and games.", EmptyParams, None, Risk.LOW, list_apps,
        windows_only=True, category="apps")
    add("launch_app", "Open an installed application by name.", AppParams, "app_launch", Risk.LOW,
        lambda c, a: _launch(c, a), windows_only=True, category="apps",
        describe=lambda a: f"Open {a.name}")
    add("launch_game", "Launch an installed game (Steam, Epic or Start Menu).", AppParams, "app_launch", Risk.LOW,
        lambda c, a: _launch(c, a, games_only=True), windows_only=True, category="apps",
        describe=lambda a: f"Launch game {a.name}")

    async def open_url(ctx, args):
        await _t(plat.open_uri, args.url)
        return ok(f"Opened {args.url} in the default browser.")

    add("open_website", "Open a website in the default browser.", UrlParams, "network_access", Risk.LOW, open_url,
        category="apps", describe=lambda a: f"Open website {a.url}")

    # ------------------------------------------------------- windows
    async def find_window(query: str):
        wins = await _t(plat.list_windows)
        q = query.lower().strip()
        q_proc = q if q.endswith(".exe") else q + ".exe"
        scored = []
        for w in wins:
            t, p = w.title.lower(), w.process.lower()
            if p == q_proc or t == q:
                s = 1.0
            elif q in t or q in p:
                s = 0.85
            else:
                s = max(difflib.SequenceMatcher(None, q, t).ratio(), difflib.SequenceMatcher(None, q, p).ratio()) * 0.8
            if s >= 0.5:
                scored.append((s, w))
        if not scored:
            raise ActionError(f"No open window matches '{query}'.", "not_found")
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    async def list_windows(ctx, args):
        wins = await _t(plat.list_windows)
        return ok(f"{len(wins)} windows open.", verified=True, windows=[w.to_dict() for w in wins])

    async def focus(ctx, args):
        w = await find_window(args.query)
        good = await _t(plat.focus_window, w.handle)
        if not good:
            return ActionResult(False, f"Windows did not allow switching to '{w.title}'.", verified=False,
                                code="focus_refused")
        return ok(f"Switched to {w.title}.", verified=True)

    async def minimize(ctx, args):
        w = await find_window(args.query)
        good = await _t(plat.minimize_window, w.handle)
        return ActionResult(good, f"Minimized {w.title}." if good else f"Could not minimize {w.title}.", verified=good)

    async def maximize(ctx, args):
        w = await find_window(args.query)
        good = await _t(plat.maximize_window, w.handle)
        return ActionResult(good, f"Maximized {w.title}." if good else f"Could not maximize {w.title}.", verified=good)

    add("list_windows", "List open windows.", EmptyParams, "system_control", Risk.LOW, list_windows,
        windows_only=True, category="windows")
    add("switch_window", "Bring a window to the front.", WindowParams, "system_control", Risk.LOW, focus,
        windows_only=True, category="windows", describe=lambda a: f"Switch to {a.query}")
    add("minimize_window", "Minimize a window.", WindowParams, "system_control", Risk.LOW, minimize,
        windows_only=True, category="windows", describe=lambda a: f"Minimize {a.query}")
    add("maximize_window", "Maximize a window.", WindowParams, "system_control", Risk.LOW, maximize,
        windows_only=True, category="windows", describe=lambda a: f"Maximize {a.query}")

    def _proc_name(name: str) -> str:
        n = name.strip().lower()
        return n if n.endswith(".exe") else n + ".exe"

    async def close_app(ctx, args):
        proc = _proc_name(args.process)
        approved = [p.lower() for p in svc.settings.current.closable_apps]
        if proc not in approved:
            raise ActionError(f"{proc} is not in the list of applications FRISTY may close. "
                              "Add it in Settings > Permissions > Closable apps.", "not_approved_app")
        if not await _t(plat.process_running, proc):
            return ok(f"{proc} is not running.", verified=True)
        n = await _t(plat.close_process_windows, proc, args.force)
        still = await _t(plat.process_running, proc)
        if still:
            return ActionResult(False, f"{proc} is still running.", verified=False)
        return ok(f"Closed {proc} ({n} process(es)).", verified=True)

    add("close_app", "Close an approved application (graceful; force optional).", CloseAppParams, "app_launch",
        Risk.HIGH, close_app, windows_only=True, category="windows",
        describe=lambda a: f"Close {_proc_name(a.process)}" + (" (force)" if a.force else ""))

    # --------------------------------------------------- audio/media
    async def get_volume(ctx, args):
        level, muted = await _t(plat.get_volume)
        return ok(f"Volume is {level}%{' (muted)' if muted else ''}.", verified=True, level=level, muted=muted)

    async def set_volume(ctx, args):
        await _t(plat.set_volume, args.level)
        try:
            level, _ = await _t(plat.get_volume)
            good = abs(level - args.level) <= 2
            return ActionResult(good, f"Volume set to {level}%." if good else
                                f"Volume is {level}%, expected {args.level}%.", verified=good, data={"level": level})
        except ImportError:
            return ok(f"Volume set to about {args.level}% (could not read it back).")

    async def change_volume(ctx, args):
        level, _ = await _t(plat.get_volume)
        target = max(0, min(100, level + args.delta))
        return await set_volume(ctx, VolumeParams(level=target))

    async def mute(ctx, args):
        await _t(plat.set_mute, args.mute)
        try:
            _, muted = await _t(plat.get_volume)
            good = muted == args.mute
            return ActionResult(good, ("Muted." if args.mute else "Unmuted.") if good else "Mute state did not change.",
                                verified=good)
        except ImportError:
            return ok("Toggled mute.")

    async def media(ctx, args):
        await _t(plat.media_key, args.command)
        return ok(f"Sent media command: {args.command.replace('_', '/')}.")

    add("get_volume", "Read the master volume.", EmptyParams, "system_control", Risk.LOW, get_volume,
        windows_only=True, category="audio")
    add("set_volume", "Set master volume to a percent.", VolumeParams, "system_control", Risk.LOW, set_volume,
        windows_only=True, category="audio", describe=lambda a: f"Set volume to {a.level}%")
    add("change_volume", "Raise or lower master volume by a percent.", VolumeDeltaParams, "system_control",
        Risk.LOW, change_volume, windows_only=True, category="audio",
        describe=lambda a: f"Change volume by {a.delta:+d}%")
    add("set_mute", "Mute or unmute the master volume.", MuteParams, "system_control", Risk.LOW, mute,
        windows_only=True, category="audio", describe=lambda a: "Mute" if a.mute else "Unmute")
    add("media_control", "Control media playback (play/pause, next, previous, stop).", MediaParams,
        "system_control", Risk.LOW, media, windows_only=True, category="audio",
        describe=lambda a: f"Media: {a.command}")

    # --------------------------------------------------------- info
    async def sysinfo(ctx, args):
        info = await _t(plat.system_info)
        return ok("System information collected.", verified=True, **info)

    add("system_info", "Show CPU, RAM, disk, GPU, battery and OS information.", EmptyParams, "system_control",
        Risk.LOW, sysinfo, category="system")

    # --------------------------------------------------------- power
    async def lock(ctx, args):
        await _t(plat.lock)
        return ok("Computer locked.")

    async def shutdown(ctx, args):
        await _t(plat.shutdown, args.delay_seconds, False)
        return ok(f"Shutdown scheduled in {args.delay_seconds} seconds. Say 'cancel shutdown' to abort.")

    async def restart(ctx, args):
        await _t(plat.shutdown, args.delay_seconds, True)
        return ok(f"Restart scheduled in {args.delay_seconds} seconds. Say 'cancel shutdown' to abort.")

    async def cancel_shutdown(ctx, args):
        await _t(plat.cancel_shutdown)
        return ok("Scheduled shutdown/restart cancelled.", verified=True)

    add("lock_computer", "Lock the computer (requires the Windows password to unlock).", EmptyParams,
        "power_management", Risk.MEDIUM, lock, windows_only=True, category="power", describe=lambda a: "Lock the computer")
    add("shutdown_computer", "Shut down the computer after a delay.", ShutdownParams, "power_management",
        Risk.HIGH, shutdown, windows_only=True, category="power",
        describe=lambda a: f"SHUT DOWN the computer in {a.delay_seconds}s")
    add("restart_computer", "Restart the computer after a delay.", ShutdownParams, "power_management",
        Risk.HIGH, restart, windows_only=True, category="power",
        describe=lambda a: f"RESTART the computer in {a.delay_seconds}s")
    add("cancel_shutdown", "Cancel a scheduled shutdown or restart.", EmptyParams, "power_management", Risk.LOW,
        cancel_shutdown, windows_only=True, category="power")

    # --------------------------------------------------------- files
    async def find_files(ctx, args):
        res = await _t(files.find_files, args.query, args.root, args.limit)
        return ok(f"Found {len(res)} file(s) matching '{args.query}'.", verified=True, files=res)

    async def search_contents(ctx, args):
        res = await _t(files.search_contents, args.text, args.root, args.limit)
        return ok(f"Found '{args.text}' in {len(res)} file(s).", verified=True, files=res)

    async def list_folder(ctx, args):
        res = await _t(files.listdir, args.path)
        return ok(f"{len(res)} item(s) in {args.path}.", verified=True, items=res)

    async def create_folder(ctx, args):
        p = await _t(files.create_folder, args.path)
        return ok(f"Created folder {p}.", verified=p.is_dir(), path=str(p))

    async def rename(ctx, args):
        p = await _t(files.rename, args.path, args.new_name)
        return ok(f"Renamed to {p.name}.", verified=p.exists(), path=str(p))

    async def copy(ctx, args):
        p = await _t(files.copy, args.source, args.destination, args.overwrite)
        return ok(f"Copied to {p}.", verified=p.exists(), path=str(p))

    async def move(ctx, args):
        p = await _t(files.move, args.source, args.destination, args.overwrite)
        return ok(f"Moved to {p}.", verified=p.exists(), path=str(p))

    async def delete(ctx, args):
        p = await _t(files.trash, args.path)
        return ok(f"Moved {p.name} to the Recycle Bin.", verified=not p.exists(), path=str(p))

    async def organize(ctx, args):
        moved = await _t(files.organize, args.path)
        total = sum(moved.values())
        return ok(f"Organized {total} file(s) into {len(moved)} folder(s).", verified=True, moved=moved)

    async def large(ctx, args):
        res = await _t(files.large_files, args.root, args.min_mb)
        return ok(f"Found {len(res)} file(s) larger than {args.min_mb:g} MB.", verified=True, files=res)

    async def dups(ctx, args):
        res = await _t(files.duplicates, args.root)
        wasted = sum(g["wasted_bytes"] for g in res)
        return ok(f"Found {len(res)} duplicate group(s) wasting {wasted / 1e6:.1f} MB.", verified=True, groups=res)

    async def read_doc(ctx, args):
        text = await _t(files.read_text, args.path)
        ctx.untrusted_seen = True
        r = ok(f"Read {len(text)} characters from {args.path}.", verified=True,
               content=fence_untrusted(text, f"file:{args.path}"))
        r.untrusted = True
        return r

    async def write_text(ctx, args):
        p = await _t(files.write_text, args.path, args.content, args.overwrite)
        return ok(f"Saved {p}.", verified=p.read_text(encoding="utf-8") == args.content, path=str(p))

    async def open_folder(ctx, args):
        p = svc.sandbox.resolve(args.path, must_exist=True)
        await _t(plat.open_path, str(p))
        return ok(f"Opened {p}.")

    add("find_files", "Find files by name in approved folders.", FindParams, "file_access", Risk.LOW, find_files,
        category="files", describe=lambda a: f"Find files '{a.query}'")
    add("search_file_contents", "Search text inside text/code files in approved folders.", ContentSearchParams,
        "file_access", Risk.LOW, search_contents, category="files")
    add("list_folder", "List the contents of an approved folder.", PathParams, "file_access", Risk.LOW, list_folder,
        category="files")
    add("create_folder", "Create a folder.", PathParams, "file_access", Risk.LOW, create_folder, category="files",
        describe=lambda a: f"Create folder {a.path}")
    add("rename_file", "Rename a file or folder.", RenameParams, "file_access", Risk.MEDIUM, rename,
        category="files", describe=lambda a: f"Rename {a.path} -> {a.new_name}")
    add("copy_file", "Copy a file or folder.", CopyMoveParams, "file_access", Risk.MEDIUM, copy, category="files",
        confirm_if=lambda a: a.overwrite, describe=lambda a: f"Copy {a.source} -> {a.destination}"
        + (" (OVERWRITE)" if a.overwrite else ""))
    add("move_file", "Move a file or folder.", CopyMoveParams, "file_access", Risk.MEDIUM, move, category="files",
        confirm_if=lambda a: a.overwrite, describe=lambda a: f"Move {a.source} -> {a.destination}"
        + (" (OVERWRITE)" if a.overwrite else ""))
    add("delete_file", "Delete a file or folder (moves it to the Recycle Bin).", PathParams, "file_access",
        Risk.HIGH, delete, category="files", describe=lambda a: f"Delete {a.path} (to Recycle Bin)")
    add("organize_folder", "Sort files in a folder (e.g. Downloads) into category subfolders.", PathParams,
        "file_access", Risk.MEDIUM, organize, category="files", confirm="always",
        describe=lambda a: f"Organize {a.path} into subfolders",
        preview=lambda a: {"plan": files.plan_organize(a.path)})
    add("find_large_files", "Find large files in approved folders.", LargeFilesParams, "file_access", Risk.LOW,
        large, category="files")
    add("find_duplicate_files", "Find duplicate files in approved folders.", DuplicateParams, "file_access",
        Risk.LOW, dups, category="files")
    add("read_document", "Read a document (txt, md, code, pdf, docx) to summarize or answer questions about it.",
        PathParams, "file_access", Risk.LOW, read_doc, category="files")
    add("create_text_file", "Create (or overwrite) a text document.", WriteTextParams, "file_access", Risk.MEDIUM,
        write_text, category="files", confirm_if=lambda a: a.overwrite,
        describe=lambda a: f"{'Overwrite' if a.overwrite else 'Create'} {a.path}")
    add("open_folder", "Open an approved folder or file with its default application.", PathParams, "file_access",
        Risk.LOW, open_folder, category="files", describe=lambda a: f"Open {a.path}")

    # -------------------------------------------------------- screen
    def provider_is_cloud() -> bool:
        return svc.settings.current.ai.provider in CLOUD_PROVIDERS

    async def take_screenshot(ctx, args):
        cap = await _t(svc.screen.capture, args.monitor, "screenshot")
        path = await _t(svc.screen.save, cap, svc.config.screenshots_dir)
        return ok(f"Screenshot saved to {path}.", verified=path.exists(), path=str(path))

    async def analyze_screen(ctx, args):
        cap = await _t(svc.screen.capture, args.monitor, "analysis")
        img_b64, factor = await _t(cap.for_model, 1600)
        elements = []
        if svc.uia.available:
            try:
                elements = [e.to_dict() for e in await _t(svc.uia.snapshot)]
            except Exception as exc:
                elements = [{"error": f"UI Automation failed: {exc}"}]
        fg = await _t(plat.foreground_window)
        ctx.untrusted_seen = True
        r = ok("Captured the screen for analysis.", verified=True, question=args.question,
               screen={"width": cap.width, "height": cap.height, "image_to_screen_factor": round(factor, 4)},
               foreground_window=fg.to_dict() if fg else None,
               ui_elements=fence_untrusted(str(elements[:150]), "ui_automation"))
        r.untrusted = True
        r.image_b64 = img_b64
        return r

    async def list_ui(ctx, args):
        els = await _t(svc.uia.snapshot)
        ctx.untrusted_seen = True
        r = ok(f"Found {len(els)} UI elements in the foreground window.", verified=True,
               elements=fence_untrusted(str([e.to_dict() for e in els]), "ui_automation"))
        r.untrusted = True
        return r

    async def locate(ctx, args):
        # 1) UI Automation (reliable), 2) vision model fallback.
        if svc.uia.available:
            try:
                found = await _t(svc.uia.find, args.description)
                if found:
                    e = found[0]
                    return ok(f"Found '{e.name}' via UI Automation.", verified=True, method="uia",
                              element_id=e.id, x=e.center[0], y=e.center[1], rect=e.rect)
            except ActionError:
                pass
        if svc.ai is None:
            raise ActionError("No AI model configured for vision-based location.")
        cap = await _t(svc.screen.capture, 1, "locate")
        img_b64, factor = await _t(cap.for_model, 1600)
        res = await svc.ai.locate_in_image(img_b64, args.description)
        if not res:
            return ActionResult(False, f"Could not find '{args.description}' on screen.", code="not_found")
        x, y = int(res[0] * factor) + cap.left, int(res[1] * factor) + cap.top
        return ok(f"Vision model located '{args.description}' at ({x}, {y}). Coordinates are approximate.",
                  verified=None, method="vision", x=x, y=y)

    add("take_screenshot", "Save a screenshot of the screen to disk.", ScreenParams, "screen_view", Risk.LOW,
        take_screenshot, category="screen")
    add("analyze_screen", "Look at the current screen (screenshot + UI elements) to explain it or find things.",
        ScreenParams, "screen_view", Risk.LOW, analyze_screen, category="screen",
        confirm_if=lambda a: provider_is_cloud(),
        describe=lambda a: "Capture the screen" + (" and SEND it to the cloud AI provider" if provider_is_cloud() else
                                                    " (analysed by your local model)"))
    add("list_ui_elements", "List buttons, fields and text in the foreground window (Windows UI Automation).",
        EmptyParams, "screen_view", Risk.LOW, list_ui, windows_only=True, category="screen")
    add("locate_on_screen", "Find the screen position of a described element (UI Automation, then vision).",
        LocateParams, "screen_view", Risk.LOW, locate, category="screen",
        confirm_if=lambda a: provider_is_cloud() and not svc.uia.available)

    # ------------------------------------------------- mouse/keyboard
    async def _verified_change(fn, *a):
        before = await _t(svc.screen.grab_quiet) if svc.settings.current.permissions.get("screen_view") else None
        await _t(fn, *a)
        if before is None:
            return None
        await asyncio.sleep(0.6)
        after = await _t(svc.screen.grab_quiet)
        if after is None:
            return None
        return cv_utils.change_ratio(before, after) > 0.002

    async def click_element(ctx, args):
        if not args.element_id and not args.name:
            raise ActionError("Give element_id or name.")
        eid = args.element_id
        if not eid:
            found = await _t(svc.uia.find, args.name)
            if not found:
                raise ActionError(f"No element named '{args.name}' in the foreground window.", "not_found")
            eid = found[0].id
        el = svc.uia.element(eid)
        if await _t(svc.uia.invoke, eid):
            return ok(f"Activated '{el.name or el.control_type}' via UI Automation.", verified=True)
        changed = await _verified_change(svc.input.click, el.center[0], el.center[1])
        return ok(f"Clicked '{el.name or el.control_type}'.", verified=changed)

    async def click_at(ctx, args):
        changed = await _verified_change(svc.input.click, args.x, args.y, args.button, 2 if args.double else 1)
        return ok(f"Clicked at ({args.x}, {args.y}).", verified=changed)

    async def scroll(ctx, args):
        await _t(svc.input.scroll, args.amount)
        return ok(f"Scrolled {'up' if args.amount > 0 else 'down'} {abs(args.amount)}.")

    async def type_text(ctx, args):
        if args.element_id:
            if await _t(svc.uia.set_text, args.element_id, args.text):
                return ok(f"Entered {len(args.text)} characters into the field.", verified=True)
            el = svc.uia.element(args.element_id)
            await _t(svc.input.click, *el.center)
        n = await _t(svc.input.type_text, args.text)
        return ok(f"Typed {n} characters.")

    async def press(ctx, args):
        await _t(svc.input.press, args.keys)
        return ok(f"Pressed {'+'.join(args.keys)}.")

    add("click_element", "Click a UI element by id (from list_ui_elements) or visible name.", ClickElementParams,
        "mouse_control", Risk.MEDIUM, click_element, windows_only=True, category="input", confirm="always",
        describe=lambda a: f"Click element {a.element_id or repr(a.name)}")
    add("click_at", "Click at screen coordinates (use locate_on_screen first).", ClickAtParams, "mouse_control",
        Risk.MEDIUM, click_at, category="input", confirm="always",
        describe=lambda a: f"{'Double-' if a.double else ''}{a.button}-click at ({a.x}, {a.y})")
    add("scroll", "Scroll the mouse wheel in the window under the cursor.", ScrollParams, "mouse_control",
        Risk.LOW, scroll, category="input", describe=lambda a: f"Scroll {a.amount}")
    add("type_text", "Type text into the focused field (or a field id). Never used for passwords.", TypeParams,
        "keyboard_control", Risk.MEDIUM, type_text, category="input", confirm="always",
        describe=lambda a: f"Type {len(a.text)} chars: {a.text[:80]!r}")
    add("press_keys", "Press a key or shortcut, e.g. ['ctrl','s'].", KeysParams, "keyboard_control", Risk.MEDIUM,
        press, category="input", confirm="always", describe=lambda a: f"Press {'+'.join(a.keys)}")

    # -------------------------------------------------------- coding
    async def write_code(ctx, args):
        res = await _t(svc.coding.write_file, args.path, args.content)
        return ok(f"Saved {res['path']}" + (f" (backup: {res['backup']})." if res["backup"] else "."),
                  verified=True, **res)

    async def create_structure(ctx, args):
        created = await _t(svc.coding.create_structure, args.root, args.files)
        return ok(f"Created {len(created)} files/folders.", verified=True, created=created)

    async def vscode(ctx, args):
        exe = await _t(svc.coding.open_vscode, args.path)
        return ok("Opened Visual Studio Code" + (f" at {args.path}." if args.path else "."), exe=exe)

    async def run_cmd(ctx, args):
        res = await _t(svc.coding.run_command, args.command, args.cwd, args.timeout_seconds)
        good = res["exit_code"] == 0
        return ActionResult(good, f"Command exited with code {res['exit_code']}.", data=res, verified=True,
                            code="ok" if good else "nonzero_exit", untrusted=True)

    def cmd_preview(a):
        from ..coding.tools import check_command

        info = check_command(a.command)
        return {"command": a.command, "cwd": str(svc.sandbox.resolve(a.cwd)), **info}

    add("write_code_file", "Create or modify a project file (shows a diff and backs up the old version).",
        CodeWriteParams, "file_access", Risk.MEDIUM, write_code, category="coding", confirm="always",
        describe=lambda a: f"Write {a.path}", preview=lambda a: svc.coding.preview_write(a.path, a.content))
    add("create_project_structure", "Create a new project's folders and files.", StructureParams, "file_access",
        Risk.MEDIUM, create_structure, category="coding", confirm="always",
        describe=lambda a: f"Create {len(a.files)} files in {a.root}",
        preview=lambda a: {"files": sorted(a.files)})
    add("open_vscode", "Open Visual Studio Code, optionally at a folder/file.", VSCodeParams, "app_launch",
        Risk.LOW, vscode, category="coding")
    add("run_terminal_command", "Run a terminal command in an approved project folder (always needs approval).",
        CommandParams, "terminal_exec", Risk.HIGH, run_cmd, category="coding", confirm="always",
        describe=lambda a: f"Run `{a.command}` in {a.cwd}", preview=cmd_preview)

    # -------------------------------------------------------- memory
    async def remember(ctx, args):
        row = await _t(svc.memory.upsert, args.category, args.key, args.value, "assistant")
        return ok(f"I'll remember: {args.key} = {args.value}.", verified=True, id=row["id"])

    async def forget(ctx, args):
        n = await _t(svc.memory.delete_by_key, args.key)
        return ActionResult(n > 0, f"Forgot {n} item(s) named '{args.key}'." if n else f"Nothing stored as '{args.key}'.",
                            verified=True)

    add("remember", "Save a user preference or fact to local memory (never passwords).", RememberParams, None,
        Risk.LOW, remember, category="memory", describe=lambda a: f"Remember {a.key}")
    add("forget", "Delete a stored memory by key.", ForgetParams, None, Risk.MEDIUM, forget, category="memory",
        describe=lambda a: f"Forget {a.key}")

    async def run_custom(ctx, args):
        if svc.automations is None:
            raise ActionError("Automations are not available.")
        return await svc.automations.run_by_name(args.name, source=ctx.source)

    add("run_custom_command", "Run one of the user's custom commands/automations by name.", CustomCommandParams,
        None, Risk.LOW, run_custom, category="automation", describe=lambda a: f"Run custom command '{a.name}'")
