import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { absoluteUrl, resolveSiteOrigin, siteUrl } from "@/lib/siteUrl";

describe("resolveSiteOrigin", () => {
  it("prefers an explicit site override when provided", () => {
    assert.equal(resolveSiteOrigin("https://taliocv.com"), "https://taliocv.com");
  });

  it("normalises away paths and trailing slashes", () => {
    assert.equal(
      resolveSiteOrigin("https://taliocv.com/app/"),
      "https://taliocv.com",
    );
  });

  it("falls back instead of throwing on a malformed value", () => {
    assert.equal(resolveSiteOrigin("not a url"), "http://localhost:3000");
  });

  it("falls back when the value is missing", () => {
    assert.equal(resolveSiteOrigin(undefined), "http://localhost:3000");
  });

  it("is always parseable, which metadataBase requires", () => {
    assert.doesNotThrow(() => new URL(resolveSiteOrigin("://broken")));
  });
});

describe("siteUrl", () => {
  it("returns a frozen origin from module load", () => {
    assert.doesNotThrow(() => new URL(siteUrl()));
  });
});

describe("absoluteUrl", () => {
  it("joins a path onto the frozen origin without doubling separators", () => {
    const url = absoluteUrl("/sitemap.xml");
    assert.equal(url, `${siteUrl()}/sitemap.xml`);
  });

  it("produces an absolute URL for the site root", () => {
    assert.equal(absoluteUrl("/"), `${siteUrl()}/`);
  });
});
