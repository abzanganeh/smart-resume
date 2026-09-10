import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeContactUrl } from "@/lib/contactUrls";
import { inferJdTargetRole } from "@/lib/jdTargetRole";

test("inferJdTargetRole skips logo alt text", () => {
  const jd = "Apollo Research logo\nForward Deployed Engineer (Product)\n\nTHE OPPORTUNITY";
  assert.equal(inferJdTargetRole(jd), "Forward Deployed Engineer (Product)");
});

test("inferJdTargetRole prefers explicit API title", () => {
  assert.equal(
    inferJdTargetRole("Apollo Research logo\nBody", "Forward Deployed Engineer (Product)"),
    "Forward Deployed Engineer (Product)",
  );
});

test("sanitizeContactUrl drops label-only values", () => {
  assert.equal(sanitizeContactUrl("linkedin", "Linkedin"), "");
  assert.equal(sanitizeContactUrl("github", "Github"), "");
});

test("sanitizeContactUrl normalizes bare URLs", () => {
  assert.equal(sanitizeContactUrl("linkedin", "linkedin.com/in/jane"), "https://linkedin.com/in/jane");
  assert.equal(sanitizeContactUrl("github", "github.com/jane"), "https://github.com/jane");
});

test("sanitizeContactUrl rejects dangerous schemes", () => {
  assert.equal(sanitizeContactUrl("linkedin", "javascript:alert(1)//x.com"), "");
  assert.equal(sanitizeContactUrl("github", "data:text/html,evil"), "");
  assert.equal(sanitizeContactUrl("linkedin", "file:///etc/passwd"), "");
  assert.equal(sanitizeContactUrl("github", "vbscript:msgbox(1)"), "");
});
