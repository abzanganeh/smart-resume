import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/siteUrl";

/**
 * Only genuinely public pages belong here.
 *
 * Everything under the prefixes guarded in `proxy.ts` redirects anonymous
 * visitors, so listing them would advertise URLs that never render content.
 * `/auth` is omitted deliberately: a sign-in form has no search value.
 */
const PUBLIC_ROUTES: { path: string; priority: number }[] = [
  { path: "/", priority: 1 },
  { path: "/checkup", priority: 0.9 },
  { path: "/legal/privacy", priority: 0.3 },
  { path: "/legal/terms", priority: 0.3 },
  { path: "/legal/ccpa", priority: 0.2 },
  { path: "/legal/sub-processors", priority: 0.2 },
  { path: "/legal/contact", priority: 0.2 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return PUBLIC_ROUTES.map(({ path, priority }) => ({
    url: absoluteUrl(path),
    lastModified,
    changeFrequency: "weekly",
    priority,
  }));
}
