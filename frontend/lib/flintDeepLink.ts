export const FLINT_IMPORT_SCHEME = "flint://import";
export const FLINT_OPEN_FALLBACK_MS = 3000;

export function buildFlintImportLink(token: string): string {
  return `${FLINT_IMPORT_SCHEME}?token=${encodeURIComponent(token)}`;
}

/**
 * Open a custom-protocol deep link without navigating the current tab away.
 *
 * Browsers require a synchronous user gesture to launch custom schemes. Callers
 * should invoke `openFlintImportCarrier()` in the click handler *before* any
 * await, then pass the returned window to `navigateFlintImportCarrier()`.
 */
export function openFlintImportCarrier(): Window | null {
  try {
    return window.open("about:blank", "_blank", "noopener,noreferrer");
  } catch {
    return null;
  }
}

export function navigateFlintImportCarrier(
  carrier: Window | null,
  deepLink: string,
): boolean {
  if (carrier && !carrier.closed) {
    try {
      carrier.location.replace(deepLink);
    } catch {
      carrier.location.href = deepLink;
    }
    window.setTimeout(() => {
      try {
        carrier.close();
      } catch {
        // Popup may already be gone once the OS takes over.
      }
    }, 500);
    return true;
  }

  // Popup blocked — try a hidden iframe without leaving Smart Resume.
  const iframe = document.createElement("iframe");
  iframe.style.display = "none";
  iframe.src = deepLink;
  document.body.appendChild(iframe);
  window.setTimeout(() => iframe.remove(), 2000);
  return false;
}
