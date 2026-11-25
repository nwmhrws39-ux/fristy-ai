// Builds the self-contained Windows x64 Python runtime (vendor/python) that the
// installer bundles. Cross-platform (Windows cmd/PowerShell, Linux, macOS):
// needs only Node, curl and tar (both built into Windows 10/11) and the repo's
// .venv (create it with `py -3.12 -m venv .venv` on Windows).
//
//   1. download python-build-standalone CPython (Windows, install_only)
//   2. build wheels for pure-Python sdist-only packages
//   3. resolve + install win_amd64 wheels with uv (correct Windows markers)
//   4. trim unneeded files
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const PY_VER = process.env.PY_VER || "3.12.8";
const PBS_TAG = process.env.PBS_TAG || "20241206";
const PYV = PY_VER.split(".").slice(0, 2).join(".");
const file = `cpython-${PY_VER}+${PBS_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz`;
const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${encodeURIComponent(file)}`;
const vendor = join(root, "vendor");
const out = join(vendor, "python");
const cache = join(vendor, "cache");
const isWin = process.platform === "win32";

function run(cmd, args, cwd = root) {
  console.log(`> ${cmd} ${args.join(" ")}`);
  execFileSync(cmd, args, { cwd, stdio: "inherit" });
}

const hostPy = process.env.HOSTPY || [join(root, ".venv", "Scripts", "python.exe"), join(root, ".venv", "bin", "python")].find(existsSync);
if (!hostPy) {
  console.error("No Python virtual environment found. Create it first:\n  Windows: py -3.12 -m venv .venv\n  Linux:   python3 -m venv .venv");
  process.exit(1);
}
const uv = join(dirname(hostPy), isWin ? "uv.exe" : "uv");

mkdirSync(cache, { recursive: true });
run(hostPy, ["-m", "pip", "install", "-q", "--disable-pip-version-check", "uv", "wheel"]);

// 1. download (curl.exe ships with Windows 10 1803+)
const tarball = file.replace("+", "_");
if (!existsSync(join(cache, tarball))) {
  console.log(`Downloading Windows CPython ${PY_VER} ...`);
  run("curl", ["-fL", "--retry", "4", "-o", `${tarball}.part`, url], cache);
  renameSync(join(cache, `${tarball}.part`), join(cache, tarball));
}
rmSync(out, { recursive: true, force: true });
rmSync(join(cache, "extract"), { recursive: true, force: true });
mkdirSync(join(cache, "extract"));
// Relative paths only: GNU tar treats "C:\..." as a remote host.
run("tar", ["-xzf", tarball, "-C", "extract"], cache);
renameSync(join(cache, "extract", "python"), out);
if (!existsSync(join(out, "python.exe"))) throw new Error("python.exe missing after extraction");
const site = join(out, "Lib", "site-packages");

// 2. pure-Python packages published only as sdists
const wheels = join(cache, "purewheels");
mkdirSync(wheels, { recursive: true });
run(hostPy, ["-m", "pip", "wheel", "--no-deps", "-q", "--disable-pip-version-check", "-w", wheels,
  "pyautogui", "pymsgbox", "pytweening", "pyscreeze", "pygetwindow", "pyrect", "mouseinfo", "pyperclip"]);

// 3. Windows wheels (uv evaluates environment markers for the TARGET platform)
run(uv, ["pip", "install", "--quiet", "--python-platform", "x86_64-pc-windows-msvc", "--python-version", PYV,
  "--only-binary", ":all:", "--find-links", wheels, "--target", site, "--no-cache",
  "-r", join(root, "backend", "requirements.txt")]);

// 4. trim
for (const p of ["Lib/test", "Lib/idlelib", "Lib/tkinter", "tcl", "Lib/ensurepip", "include", "Lib/site-packages/cv2/data"]) {
  rmSync(join(out, p), { recursive: true, force: true });
}
(function prune(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (!statSync(p).isDirectory()) continue;
    if (name === "__pycache__") rmSync(p, { recursive: true, force: true });
    else prune(p);
  }
})(out);
rmSync(join(cache, "extract"), { recursive: true, force: true });
console.log(`Windows Python runtime ready: ${out}`);
