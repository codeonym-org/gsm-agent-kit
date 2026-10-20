import { fileURLToPath } from "node:url";
import { build } from "esbuild";

await build({
  absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
  entryPoints: ["server/index.ts"],
  outfile: "dist-server/index.mjs",
  bundle: true,
  platform: "node",
  target: "node24",
  format: "esm",
  // ws has optional native accelerators; its built-in JavaScript paths work without them.
  external: ["bufferutil", "utf-8-validate"],
  banner: {
    js: 'import { createRequire } from "node:module"; const require = createRequire(import.meta.url);',
  },
  legalComments: "linked",
});
