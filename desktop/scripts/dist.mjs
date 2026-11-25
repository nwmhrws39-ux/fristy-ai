// `npm run dist` -> desktop/release/FRISTY-AI-Setup-<version>-x64.exe
//  1. bundled Windows Python runtime (vendor/python) - built once, then reused
//  2. renderer + Electron bundles
//  3. Windows: electron-builder NSIS (embeds the exe icon)
//     Linux/macOS: electron-builder --dir + makensis with installer/fristy.nsi (no Wine needed)
import { execSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const desktop = join(dirname(fileURLToPath(import.meta.url)), "..");
const root = join(desktop, "..");
const isWin = process.platform === "win32";
const version = JSON.parse(readFileSync(join(desktop, "package.json"), "utf8")).version;

function run(cmd, cwd = desktop) {
  console.log(`\n> ${cmd}`);
  execSync(cmd, { cwd, stdio: "inherit", env: process.env });
}

function has(cmd) {
  // Only used for makensis on non-Windows hosts.
  return spawnSync(isWin ? "where" : "which", [cmd], { stdio: "ignore", shell: isWin }).status === 0;
}

// 1. Python runtime (Node + curl + tar only - no bash needed, also on Windows)
if (!existsSync(join(root, "vendor", "python", "python.exe"))) {
  run(`"${process.execPath}" scripts/build_windows_python.mjs`, root);
} else {
  console.log("Using existing vendor/python (delete it to rebuild).");
}

// 2. app bundles
run("npm run build");

// 3. installer
if (isWin) {
  run("npx electron-builder --win nsis --x64 --publish never -c.win.signAndEditExecutable=true");
} else {
  if (!has("makensis")) {
    console.error("makensis is required on this OS (e.g. `sudo apt-get install nsis`).");
    process.exit(1);
  }
  run("npx electron-builder --win dir --x64 --publish never");
  run(`makensis -V2 -DVERSION=${version} fristy.nsi`, join(root, "installer"));
}
const exe = join(desktop, "release", `FRISTY-AI-Setup-${version}-x64.exe`);
if (!existsSync(exe)) {
  console.error("Installer was not produced:", exe);
  process.exit(1);
}
console.log(`\n✅ Installer ready: ${exe}`);
