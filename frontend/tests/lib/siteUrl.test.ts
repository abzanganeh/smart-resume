import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { absoluteUrl, siteUrl } from "@/lib/siteUrl";

const ENV_KEYS = ["NEXT_PUBLIC_SITE_URL", "NEXTAUTH_URL"] as const;
const saved = new Map(ENV_KEYS.map((key) => [key, process.env[key]]));

/**
 * These read env at call time rather than module load, so a static import is
 * enough. The surrounding env is restored after each case so this file cannot
 * leak into the rest of the suite.
 */
afterEach(() => {
  for (const key of ENV_KEYS) {
    const value = saved.get(key);
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

describe("siteUrl", () => {
  it("prefers the explicit site override", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://taliocv.com";
    process.env.NEXTAUTH_URL = "https://auth.example";
    assert.equal(siteUrl(), "https://taliocv.com");
  });

  it("falls back to the NextAuth origin, which every environment sets", () => {
    delete process.env.NEXT_PUBLIC_SITE_URL;
    process.env.NEXTAUTH_URL = "https://staging.taliocv.com";
    assert.equal(siteUrl(), "https://staging.taliocv.com");
  });

  it("normalises away paths and trailing slashes", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://taliocv.com/app/";
    assert.equal(siteUrl(), "https://taliocv.com");
  });

  it("falls back instead of throwing on a malformed value", () => {
    // This runs during module evaluation of the root layout: throwing here
    // would take down every route to save one meta tag.
    process.env.NEXT_PUBLIC_SITE_URL = "not a url";
    delete process.env.NEXTAUTH_URL;
    assert.equal(siteUrl(), "http://localhost:3000");
  });

  it("is always parseable, which metadataBase requires", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "://broken";
    assert.doesNotThrow(() => new URL(siteUrl()));
  });
});

describe("absoluteUrl", () => {
  it("joins a path onto the origin without doubling separators", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://taliocv.com/";
    assert.equal(absoluteUrl("/sitemap.xml"), "https://taliocv.com/sitemap.xml");
  });

  it("produces an absolute URL for the site root", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://taliocv.com";
    assert.equal(absoluteUrl("/"), "https://taliocv.com/");
  });
});
