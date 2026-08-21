import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/siteUrl";

/**
 * Mirrors the guarded prefixes in `proxy.ts`. Crawling them produces a redirect
 * to `/auth` rather than content, so the only thing indexing them achieves is
 * wasted budget and a pile of duplicate sign-in pages in the index.
 */
const PRIVATE_PREFIXES = [
  "/admin",
  "/api/",
  "/auth",
  "/billing",
  "/cover-letter",
  "/dashboard",
  "/fit",
  "/jobs",
  "/notifications",
  "/onboarding",
  "/profile",
  "/session",
  "/settings",
  "/tracker",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: PRIVATE_PREFIXES,
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: absoluteUrl("/"),
  };
}
