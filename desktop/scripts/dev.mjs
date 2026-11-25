// Dev runner: Vite dev server + Electron (with the repo's Python venv backend).
import { spawn } from "node:child_process";
import { createServer } from "vite";

const server = await createServer({ configFile: "vite.config.ts" });
await server.listen();
await import("./build-electron.mjs");
const electron = (await import("electron")).default;
const child = spawn(electron, ["."], { stdio: "inherit", env: { ...process.env, FRISTY_DEV_URL: "http://127.0.0.1:5173" } });
child.on("exit", async (code) => { await server.close(); process.exit(code ?? 0); });
