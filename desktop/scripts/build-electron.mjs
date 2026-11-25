import { build } from "esbuild";

const common = { bundle: true, platform: "node", target: "node20", external: ["electron"], sourcemap: false, minify: true, format: "cjs" };
await build({ ...common, entryPoints: ["electron/main.ts"], outfile: "dist-electron/main.cjs" });
await build({ ...common, entryPoints: ["electron/preload.ts"], outfile: "dist-electron/preload.cjs" });
console.log("electron bundles built");
