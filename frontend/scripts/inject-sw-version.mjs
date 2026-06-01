import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const sha = process.env.NEXT_PUBLIC_GIT_SHA || process.env.VERCEL_GIT_COMMIT_SHA || "dev";
const vapid = process.env.NEXT_PUBLIC_WEB_PUSH_VAPID_PUBLIC_KEY || "";

const template = readFileSync(join(root, "public", "sw.template.js"), "utf8");
const output = template
  .replace(
    'const SW_VERSION = process.env.NEXT_PUBLIC_GIT_SHA || "dev";',
    `const SW_VERSION = ${JSON.stringify(sha)};`,
  )
  .replaceAll("__VAPID_PUBLIC_KEY__", vapid);

writeFileSync(join(root, "public", "sw.js"), output);
console.log(`Generated public/sw.js (SW_VERSION=${sha})`);
