/**
 * FRISTY AI - Electron main process.
 *
 * Responsibilities:
 *  - start/supervise the Python backend on 127.0.0.1 with a random per-session token
 *  - create the frameless, sandboxed UI window (full dashboard + compact floating mode)
 *  - system tray, global shortcuts (toggle, compact, push-to-talk, EMERGENCY STOP)
 *  - start-with-Windows, strict CSP, navigation and permission lockdown
 */
import { app, BrowserWindow, dialog, globalShortcut, ipcMain, Menu, nativeImage, session, shell, Tray, screen } from "electron";
import { ChildProcess, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import * as fs from "node:fs";
import * as http from "node:http";
import * as net from "node:net";
import * as path from "node:path";

const isDev = !!process.env.FRISTY_DEV_URL;
const TOKEN = randomBytes(32).toString("base64url");
let PORT = 0;
let backend: ChildProcess | null = null;
let backendRestarts = 0;
let backendReady = false;
let quitting = false;
let win: BrowserWindow | null = null;
let tray: Tray | null = null;
let compact = false;
let trayMode = true;
let lastBackendError = "";

const FULL = { width: 1320, height: 840, minWidth: 980, minHeight: 640 };
const COMPACT = { width: 400, height: 600 };

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

function log(...args: unknown[]) {
  // eslint-disable-next-line no-console
  console.log("[fristy]", ...args);
}

function resourcePath(...p: string[]): string {
  return app.isPackaged ? path.join(process.resourcesPath, ...p) : path.join(__dirname, "..", "..", ...p);
}

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      const port = typeof addr === "object" && addr ? addr.port : 0;
      srv.close(() => resolve(port));
    });
  });
}

function pythonCommand(): { cmd: string; args: string[]; cwd: string; env: Record<string, string> } {
  if (app.isPackaged) {
    const py = process.platform === "win32"
      ? path.join(process.resourcesPath, "python", "python.exe")
      : path.join(process.resourcesPath, "python", "bin", "python3");
    const backendDir = path.join(process.resourcesPath, "backend");
        // -s: ignore the user's site-packages. (Not -I: isolated mode would also ignore PYTHONPATH.)
    return { cmd: py, args: ["-s", "-m", "fristy.main"], cwd: backendDir,
             env: { PYTHONPATH: backendDir, PYTHONNOUSERSITE: "1", PYTHONHOME: "", PYTHONSTARTUP: "" } };
  }
  const repo = path.join(__dirname, "..", "..");
  const venvPy = process.platform === "win32" ? path.join(repo, ".venv", "Scripts", "python.exe") : path.join(repo, ".venv", "bin", "python");
  const cmd = process.env.FRISTY_PYTHON || (fs.existsSync(venvPy) ? venvPy : process.platform === "win32" ? "python" : "python3");
  return { cmd, args: ["-m", "fristy.main"], cwd: path.join(repo, "backend"), env: { PYTHONPATH: path.join(repo, "backend") } };
}

function startBackend(): void {
  const { cmd, args, cwd, env } = pythonCommand();
  log("starting backend", cmd, args.join(" "), "port", PORT);
  backendReady = false;
  backend = spawn(cmd, args, {
    cwd,
    env: {
      ...process.env,
      ...env,
      FRISTY_PORT: String(PORT),
      FRISTY_TOKEN: TOKEN,
      FRISTY_DATA_DIR: app.getPath("userData"),
      PYTHONUTF8: "1",
      PYTHONUNBUFFERED: "1",
    },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  backend.stdout?.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  backend.stderr?.on("data", (d) => {
    const text = String(d);
    if (/(ERROR|CRITICAL|Traceback|Error:|No module named)/.test(text)) lastBackendError = text.slice(-2000);
    process.stderr.write(`[backend] ${d}`);
  });
  backend.on("error", (err) => {
    lastBackendError = `Could not start the FRISTY backend: ${err.message}`;
    win?.webContents.send("backend:status", { ready: false, error: lastBackendError });
  });
  backend.on("exit", (code) => {
    log("backend exited", code);
    backendReady = false;
    backend = null;
    if (quitting) return;
    win?.webContents.send("backend:status", { ready: false, error: `Backend stopped (code ${code}). ${lastBackendError}` });
    if (backendRestarts < 3) {
      backendRestarts++;
      setTimeout(startBackend, 1500 * backendRestarts);
      void waitForBackend();
    }
  });
}

function health(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port: PORT, path: "/health", timeout: 1500 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(timeoutMs = 60000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await health()) {
      backendReady = true;
      backendRestarts = 0;
      win?.webContents.send("backend:status", { ready: true });
      void applyBackendSettings();
      return true;
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  win?.webContents.send("backend:status", { ready: false, error: `Backend did not start within ${timeoutMs / 1000}s. ${lastBackendError}` });
  return false;
}

function backendRequest(method: string, p: string, body?: unknown): Promise<any> {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? undefined : Buffer.from(JSON.stringify(body));
    const req = http.request(
      { host: "127.0.0.1", port: PORT, path: p, method, timeout: 5000,
        headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json", ...(data ? { "Content-Length": data.length } : {}) } },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "null"));
          } catch (e) {
            reject(e);
          }
        });
      },
    );
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}

// ---------------------------------------------------------------- shortcuts
interface Shortcuts { toggle_window: string; emergency_stop: string; compact_mode: string; push_to_talk: string }
let shortcuts: Shortcuts = {
  toggle_window: "CommandOrControl+Shift+F",
  emergency_stop: "CommandOrControl+Shift+F12",
  compact_mode: "CommandOrControl+Shift+C",
  push_to_talk: "CommandOrControl+Shift+Space",
};

async function emergencyStop(): Promise<void> {
  log("EMERGENCY STOP");
  win?.webContents.send("emergency-stop");
  try {
    await backendRequest("POST", "/api/emergency-stop");
  } catch (e) {
    log("emergency stop request failed", e);
  }
}

function registerShortcuts(): string[] {
  globalShortcut.unregisterAll();
  const failed: string[] = [];
  const reg = (accel: string, fn: () => void) => {
    if (!accel) return;
    try {
      if (!globalShortcut.register(accel, fn)) failed.push(accel);
    } catch {
      failed.push(accel);
    }
  };
  reg(shortcuts.emergency_stop, () => void emergencyStop());
  reg(shortcuts.toggle_window, toggleWindow);
  reg(shortcuts.compact_mode, () => setCompact(!compact));
  reg(shortcuts.push_to_talk, () => {
    showWindow();
    win?.webContents.send("push-to-talk");
  });
  if (failed.length) log("shortcuts failed to register:", failed);
  return failed;
}

async function applyBackendSettings(): Promise<void> {
  try {
    const s = await backendRequest("GET", "/api/settings");
    shortcuts = {
      toggle_window: s.shortcuts.toggle_window,
      emergency_stop: s.shortcuts.emergency_stop,
      compact_mode: s.shortcuts.compact_mode,
      push_to_talk: s.voice.push_to_talk_shortcut,
    };
    trayMode = !!s.startup.tray_mode;
    if (app.isPackaged && process.platform === "win32") {
      app.setLoginItemSettings({ openAtLogin: !!s.startup.start_with_windows, args: ["--hidden"] });
    }
    const failed = registerShortcuts();
    win?.webContents.send("shortcuts:status", { failed });
  } catch (e) {
    log("could not load settings", e);
  }
}

// ------------------------------------------------------------------ window
function showWindow() {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function toggleWindow() {
  if (!win) return;
  if (win.isVisible() && win.isFocused()) win.hide();
  else showWindow();
}

function setCompact(on: boolean) {
  if (!win) return;
  compact = on;
  const area = screen.getDisplayMatching(win.getBounds()).workArea;
  if (on) {
    win.setMinimumSize(320, 420);
    win.setBounds({ width: COMPACT.width, height: COMPACT.height, x: area.x + area.width - COMPACT.width - 24, y: area.y + area.height - COMPACT.height - 24 }, true);
    win.setAlwaysOnTop(true, "floating");
  } else {
    win.setAlwaysOnTop(false);
    win.setMinimumSize(FULL.minWidth, FULL.minHeight);
    win.setBounds({ width: FULL.width, height: FULL.height, x: area.x + Math.round((area.width - FULL.width) / 2), y: area.y + Math.round((area.height - FULL.height) / 2) }, true);
  }
  win.webContents.send("window:compact", compact);
  showWindow();
}

function iconPath(): string {
  const p = resourcePath(app.isPackaged ? "icon.png" : "desktop/build/icon.png");
  return fs.existsSync(p) ? p : "";
}

function createWindow(startHidden: boolean) {
  win = new BrowserWindow({
    ...FULL,
    show: false,
    frame: false,
    backgroundColor: "#040206",
    title: "FRISTY AI",
    icon: iconPath() || undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
    },
  });
  win.once("ready-to-show", () => {
    if (!startHidden) win?.show();
  });
  win.on("close", (e) => {
    if (!quitting && trayMode && tray) {
      e.preventDefault();
      win?.hide();
    }
  });
  win.on("maximize", () => win?.webContents.send("window:maximized", true));
  win.on("unmaximize", () => win?.webContents.send("window:maximized", false));
  // Lock down navigation: the UI never navigates; external links open in the browser.
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(process.env.FRISTY_DEV_URL || "file://")) e.preventDefault();
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  if (isDev) void win.loadURL(process.env.FRISTY_DEV_URL!);
  else void win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
}

function createTray() {
  const icon = iconPath();
  const image = icon ? nativeImage.createFromPath(icon).resize({ width: 16, height: 16 }) : nativeImage.createEmpty();
  tray = new Tray(image);
  tray.setToolTip("FRISTY AI");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open FRISTY AI", click: () => { setCompact(false); } },
      { label: "Compact assistant", click: () => setCompact(true) },
      { type: "separator" },
      { label: "Emergency stop", click: () => void emergencyStop() },
      { type: "separator" },
      { label: "Quit", click: () => { quitting = true; app.quit(); } },
    ]),
  );
  tray.on("click", toggleWindow);
}

function installSecurity() {
  const csp = [
    "default-src 'self'",
    `connect-src 'self' http://127.0.0.1:${PORT} ws://127.0.0.1:${PORT}${isDev ? " ws://127.0.0.1:5173 http://127.0.0.1:5173" : ""}`,
    "img-src 'self' data: blob:",
    "media-src 'self' blob: data:",
    "font-src 'self' data:",
    `script-src 'self'${isDev ? " 'unsafe-inline' 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
  ].join("; ");
  session.defaultSession.webRequest.onHeadersReceived((details, cb) => {
    cb({ responseHeaders: { ...details.responseHeaders, "Content-Security-Policy": [csp] } });
  });
  // Only the microphone (for voice) may be requested; everything else is denied.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb, details) => {
    const okMedia = permission === "media" && (details as any).mediaTypes?.every((t: string) => t === "audio");
    cb(!!okMedia);
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => permission === "media");
}

// --------------------------------------------------------------------- ipc
ipcMain.handle("config:get", () => ({ port: PORT, token: TOKEN, ready: backendReady, error: lastBackendError, platform: process.platform, version: app.getVersion(), compact }));
ipcMain.handle("window:minimize", () => win?.minimize());
ipcMain.handle("window:maximize", () => (win?.isMaximized() ? win.unmaximize() : win?.maximize()));
ipcMain.handle("window:close", () => win?.close());
ipcMain.handle("window:compact", (_e, on: boolean) => setCompact(!!on));
ipcMain.handle("settings:apply", () => applyBackendSettings());
ipcMain.handle("backend:restart", async () => {
  backendRestarts = 0;
  if (backend) backend.kill();
  else startBackend();
  return waitForBackend();
});
ipcMain.handle("shell:openExternal", (_e, url: string) => {
  if (typeof url === "string" && /^https?:\/\//i.test(url)) return shell.openExternal(url);
  return false;
});
ipcMain.handle("emergency-stop", () => emergencyStop());
ipcMain.handle("dialog:pickFolder", async () => {
  if (!win) return null;
  const r = await dialog.showOpenDialog(win, { properties: ["openDirectory", "createDirectory"] });
  return r.canceled ? null : r.filePaths[0] ?? null;
});

// --------------------------------------------------------------- lifecycle
app.on("second-instance", () => showWindow());
app.whenReady().then(async () => {
  app.setAppUserModelId("ai.fristy.desktop");
  PORT = Number(process.env.FRISTY_FIXED_PORT) || (await freePort());
  installSecurity();
  startBackend();
  const hidden = process.argv.includes("--hidden");
  createWindow(hidden);
  createTray();
  registerShortcuts();
  void waitForBackend();
});
app.on("before-quit", () => {
  quitting = true;
});
app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  if (backend) {
    backend.kill();
    backend = null;
  }
});
app.on("window-all-closed", () => {
  if (!trayMode) app.quit();
});
