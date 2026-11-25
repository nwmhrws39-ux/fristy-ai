// Writes release-notes.md with the CHANGELOG.md section for the given version.
import { readFileSync, writeFileSync } from "node:fs";

const v = process.argv[2];
const md = readFileSync("CHANGELOG.md", "utf8");
const start = md.indexOf(`## ${v}`);
let body = `FRISTY AI ${v}`;
if (start >= 0) {
  const rest = md.slice(start);
  const next = rest.indexOf("\n## ", 3);
  body = rest.slice(rest.indexOf("\n") + 1, next > 0 ? next : undefined).trim();
}
writeFileSync("release-notes.md", body + "\n");
console.log(body);
