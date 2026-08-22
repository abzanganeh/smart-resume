import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import assert from "node:assert/strict";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");

function readSource(relativePath: string): string {
  return readFileSync(join(repoRoot, relativePath), "utf8");
}

describe("trial claim liability — marketing surfaces", () => {
  it("PricingSection does not advertise a free trial", () => {
    const source = readSource("components/marketing/PricingSection.tsx");
    assert.equal(source.includes("-day trial"), false);
    assert.equal(source.includes("free trial"), false);
  });

  it("billing plan cards do not advertise a free trial badge", () => {
    const source = readSource("app/billing/page.tsx");
    assert.equal(source.includes("-day free trial"), false);
    assert.equal(/plan\.trial_days\s*&&/.test(source), false);
  });
});
