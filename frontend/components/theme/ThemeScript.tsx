import { headers } from "next/headers";
import Script from "next/script";

/** Applies saved theme before paint. Must use next/script — a React <script> in layout is not executed on the client. */
export async function ThemeScript() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <Script id="sr-theme-init" strategy="beforeInteractive" nonce={nonce}>
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
