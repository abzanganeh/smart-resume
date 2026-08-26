import { headers } from "next/headers";

const THEME_INIT_SOURCE = `(function () {
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
})();`;

/**
 * Applies saved theme before paint.
 *
 * Uses a plain <script> in the server layout head instead of next/script.
 * next/script's beforeInteractive wrapper re-hydrates an inner <script> whose
 * nonce attribute disagrees with the streamed RSC payload in dev (server
 * renders nonce="", client expects the CSP nonce), which trips React's
 * hydration warning even with suppressHydrationWarning on the wrapper.
 * A single server-rendered script tag executes from the initial HTML and
 * keeps the nonce on the element React actually hydrates.
 */
export async function ThemeScript() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <script
      id="sr-theme-init"
      nonce={nonce}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: THEME_INIT_SOURCE }}
    />
  );
}
