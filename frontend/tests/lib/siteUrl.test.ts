import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { absoluteUrl, isExplicitLocalHttpSite, isLocalHttpOrigin, resolveSiteOrigin, siteUrl } from "@/lib/siteUrl";

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

describe("isLocalHttpOrigin", () => {
  it("treats loopback HTTP as local staging", () => {
    assert.equal(isLocalHttpOrigin("http://localhost:3001"), true);
    assert.equal(isLocalHttpOrigin("http://127.0.0.1:3001"), true);
  });

  it("rejects HTTPS loopback and remote HTTP", () => {
    assert.equal(isLocalHttpOrigin("https://localhost:3001"), false);
    assert.equal(isLocalHttpOrigin("http://evil.com"), false);
    assert.equal(isLocalHttpOrigin("https://flintapply.com"), false);
  });
});

describe("isExplicitLocalHttpSite", () => {
  it("fails closed when site env is unset", () => {
    assert.equal(isExplicitLocalHttpSite(undefined), false);
    assert.equal(isExplicitLocalHttpSite(""), false);
  });

  it("allows explicit loopback HTTP staging origins", () => {
    assert.equal(
      isExplicitLocalHttpSite("http://localhost:3001"),
      true,
    );
  });

  it("does not treat HTTPS production as local HTTP", () => {
    assert.equal(
      isExplicitLocalHttpSite("https://flintapply.com"),
      false,
    );
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
