import type { MetadataRoute } from "next";
import { absoluteUrl, siteUrl } from "@/lib/siteUrl";

/**
 * Pages with no public search value. Several are session-gated in the app; others
 * are client-guarded only. Blocking them here saves crawl budget — it is not
 * access control.
 */
const PRIVATE_PREFIXES = [
  "/admin",
  "/api/",
  "/auth",
  "/billing",
  "/career-watch",
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
    host: new URL(siteUrl()).host,
  };
}
