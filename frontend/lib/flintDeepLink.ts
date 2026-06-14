export const FLINT_IMPORT_SCHEME = "flint://import";
export const FLINT_OPEN_FALLBACK_MS = 3000;

export function buildFlintImportLink(token: string): string {
  return `${FLINT_IMPORT_SCHEME}?token=${encodeURIComponent(token)}`;
}

/**
 * Open a placeholder window synchronously on click so a later async handoff can
 * assign `flint://…` without losing the user-gesture chain (required on Linux).
 */
export function openFlintImportCarrier(): Window | null {
  try {
    return window.open("about:blank", "flint_handoff", "noopener,noreferrer");
  } catch {
    return null;
  }
}

function closeCarrier(carrier: Window | null): void {
  if (!carrier || carrier.closed) return;
  for (const delayMs of [0, 50, 250, 1000]) {
    window.setTimeout(() => {
      try {
        carrier.close();
      } catch {
        // Popup may already be gone once the OS takes over.
      }
    }, delayMs);
  }
}

function navigateViaHiddenAnchor(deepLink: string): void {
  const anchor = document.createElement("a");
  anchor.href = deepLink;
  anchor.rel = "noopener noreferrer";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

export function navigateFlintImportCarrier(
  carrier: Window | null,
  deepLink: string,
): boolean {
  if (carrier && !carrier.closed) {
    // One navigation only — fallback anchor causes duplicate OS handler calls on Linux.
    carrier.location.href = deepLink;
    closeCarrier(carrier);
    return true;
  }

  navigateViaHiddenAnchor(deepLink);
  return false;
}
