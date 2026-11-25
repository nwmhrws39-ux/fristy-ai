/** Minimal, typed bridge between the sandboxed renderer and the main process. */
import { contextBridge, ipcRenderer, IpcRendererEvent } from "electron";

type Listener = (...args: any[]) => void;
const CHANNELS = ["backend:status", "emergency-stop", "push-to-talk", "window:compact", "window:maximized", "shortcuts:status"] as const;

contextBridge.exposeInMainWorld("fristy", {
  getConfig: () => ipcRenderer.invoke("config:get"),
  minimize: () => ipcRenderer.invoke("window:minimize"),
  maximize: () => ipcRenderer.invoke("window:maximize"),
  close: () => ipcRenderer.invoke("window:close"),
  setCompact: (on: boolean) => ipcRenderer.invoke("window:compact", on),
  applySettings: () => ipcRenderer.invoke("settings:apply"),
  restartBackend: () => ipcRenderer.invoke("backend:restart"),
  openExternal: (url: string) => ipcRenderer.invoke("shell:openExternal", url),
  emergencyStop: () => ipcRenderer.invoke("emergency-stop"),
  show: () => ipcRenderer.invoke("window:show"),
  pickFolder: () => ipcRenderer.invoke("dialog:pickFolder"),
  on: (channel: (typeof CHANNELS)[number], fn: Listener) => {
    if (!CHANNELS.includes(channel)) throw new Error("invalid channel");
    const wrapped = (_e: IpcRendererEvent, ...args: any[]) => fn(...args);
    ipcRenderer.on(channel, wrapped);
    return () => ipcRenderer.removeListener(channel, wrapped);
  },
});
