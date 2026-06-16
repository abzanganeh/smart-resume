"use client";

import { BrandLogo } from "@/components/brand/BrandLogo";

/** Fallback page when the extension tab listener misses the redirect. */
export default function ExtensionGoogleCallbackPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-4 px-6 text-center">
      <BrandLogo className="h-8 w-auto" />
      <h1 className="text-xl font-semibold text-foreground">Sign-in complete</h1>
      <p className="text-muted-foreground max-w-sm">
        You can close this tab and return to the Flint browser extension.
      </p>
    </main>
  );
}
