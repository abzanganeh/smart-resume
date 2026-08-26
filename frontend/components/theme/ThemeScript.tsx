import { headers } from "next/headers";
import Script from "next/script";

/**
 * Applies saved theme before paint. Must use next/script — a React <script> in
 * layout is not executed on the client.
 *
 * The rendered <script> element carries the per-request CSP nonce. Next's dev
 * pipeline serialises nonces differently between the initial SSR HTML and the
 * streamed RSC payload React uses to hydrate, which surfaces as a benign
 * hydration warning for the nonce attribute. The script executes correctly
 * from the SSR pass with the right nonce; the mismatch does not affect
 * runtime. Suppress the warning on this specific element to keep the DevTools
 * console signal-to-noise usable.
 */
export async function ThemeScript() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <Script
      id="sr-theme-init"
      strategy="beforeInteractive"
      nonce={nonce}
      suppressHydrationWarning
    >
      {`(function () {
  try {
    var key = "sr-theme";
    var stored = localStorage.getItem(key);
    var dark =
      stored === "dark" ||
      (stored !== "light" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    var root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(dark ? "dark" : "light");
    root.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {}
})();`}
    </Script>
  );
}
