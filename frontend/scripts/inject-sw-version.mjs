import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const sha =
  process.env.NEXT_PUBLIC_GIT_SHA ||
  process.env.VERCEL_GIT_COMMIT_SHA ||
  "dev";
const template = readFileSync(join(root, "public", "sw.template.js"), "utf8");
const output = template.replaceAll("__BUILD_SHA__", sha);
writeFileSync(join(root, "public", "sw.js"), output);
console.log(`Generated public/sw.js (SW_VERSION=${sha})`);
