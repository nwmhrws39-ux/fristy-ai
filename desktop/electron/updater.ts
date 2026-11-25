/**
 * Self-update from GitHub Releases.
 *  - check: GET api.github.com/repos/<owner>/<repo>/releases/latest, compare semver with app version
 *  - install: download FRISTY-AI-Setup-<v>-x64.exe (+ .sha256), verify SHA-256, run it silently
 *    (/S --force-run relaunches the app), then quit so files can be replaced.
 * Only github.com URLs from the configured repository are accepted.
 */
import { app, net, shell } from "electron";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";

export const UPDATE_REPO = { owner: "nwmhrws39-ux", repo: "fristy-ai" };
const ASSET = /^FRISTY-AI-Setup-(\d+\.\d+\.\d+)-x64\.exe$/;

export interface UpdateInfo {
  current: string;
  latest: string | null;
  available: boolean;
  notes: string;
  publishedAt: string | null;
  asset: { name: string; url: string; size: number } | null;
  checksumUrl: string | null;
  releaseUrl: string | null;
  error?: string;
}

export function compareVersions(a: string, b: string): number {
  const pa = a.replace(/^v/, "").split(/[.-]/).map((x) => parseInt(x, 10) || 0);
  const pb = b.replace(/^v/, "").split(/[.-]/).map((x) => parseInt(x, 10) || 0);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0) ? 1 : -1;
  }
  return 0;
}

function trusted(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && (u.hostname === "github.com" || u.hostname === "api.github.com") &&
      (u.hostname === "api.github.com" || u.pathname.startsWith(`/${UPDATE_REPO.owner}/${UPDATE_REPO.repo}/releases/download/`));
  } catch {
    return false;
  }
}

export async function checkForUpdate(): Promise<UpdateInfo> {
  const current = app.getVersion();
  const base: UpdateInfo = { current, latest: null, available: false, notes: "", publishedAt: null, asset: null, checksumUrl: null, releaseUrl: null };
  try {
    const res = await net.fetch(`https://api.github.com/repos/${UPDATE_REPO.owner}/${UPDATE_REPO.repo}/releases/latest`, {
      headers: { Accept: "application/vnd.github+json", "User-Agent": "FRISTY-AI-Updater" },
    });
    if (res.status === 404) return { ...base, error: "no_release" };
    if (!res.ok) return { ...base, error: `GitHub ${res.status}` };
    const rel: any = await res.json();
    const exe = (rel.assets || []).find((a: any) => ASSET.test(a.name));
    const sum = exe && (rel.assets || []).find((a: any) => a.name === `${exe.name}.sha256`);
    const latest = String(rel.tag_name || "").replace(/^v/, "");
    return {
      ...base,
      latest,
      available: !!exe && compareVersions(latest, current) > 0,
      notes: String(rel.body || "").slice(0, 4000),
      publishedAt: rel.published_at || null,
      asset: exe ? { name: exe.name, url: exe.browser_download_url, size: exe.size } : null,
      checksumUrl: sum ? sum.browser_download_url : null,
      releaseUrl: rel.html_url || null,
    };
  } catch (e) {
    return { ...base, error: (e as Error).message };
  }
}

export async function downloadAndInstall(info: UpdateInfo, onProgress: (p: { received: number; total: number }) => void,
                                         beforeQuit: () => void): Promise<void> {
  if (!info.asset || !trusted(info.asset.url)) throw new Error("Untrusted or missing update file.");
  if (!info.checksumUrl || !trusted(info.checksumUrl)) throw new Error("The release has no SHA-256 checksum; refusing to install.");
  if (process.platform !== "win32") {
    await shell.openExternal(info.releaseUrl || info.asset.url);
    return;
  }
  const sumRes = await net.fetch(info.checksumUrl);
  if (!sumRes.ok) throw new Error(`Checksum download failed (${sumRes.status})`);
  const expected = (await sumRes.text()).trim().split(/\s+/)[0].toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(expected)) throw new Error("Invalid checksum file.");

  const dir = path.join(app.getPath("temp"), "fristy-update");
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, info.asset.name);
  const res = await net.fetch(info.asset.url);
  if (!res.ok || !res.body) throw new Error(`Download failed (${res.status})`);
  const total = Number(res.headers.get("content-length")) || info.asset.size;
  const hash = createHash("sha256");
  const out = fs.createWriteStream(file);
  let received = 0;
  const reader = res.body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    hash.update(value);
    received += value.length;
    if (!out.write(value)) await new Promise((r) => out.once("drain", r));
    onProgress({ received, total });
  }
  await new Promise<void>((resolve, reject) => out.end((err?: Error | null) => (err ? reject(err) : resolve())));
  const actual = hash.digest("hex");
  if (actual !== expected) {
    fs.rmSync(file, { force: true });
    throw new Error("Checksum mismatch - the download is corrupted or was tampered with. Update cancelled.");
  }
  // Silent install, then the installer relaunches FRISTY (--force-run).
  const child = spawn(file, ["/S", "--updated", "--force-run"], { detached: true, stdio: "ignore", windowsHide: false });
  child.unref();
  beforeQuit();
  setTimeout(() => app.quit(), 500);
}
