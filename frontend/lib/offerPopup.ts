/** Session-scoped offer popup helpers (M21 slice 4). */

export type OfferPopupTrigger = "exit_intent" | "post_exhaustion";

export const OFFER_POPUP_SESSION_KEY = "talio_offer_popup_shown";
export const CREDITS_EXHAUSTED_EVENT = "talio:credits-exhausted";

export interface BillingPopupOffer {
  code: string;
  grant_type: string;
  expires_at: string | null;
  is_active: boolean;
  is_redeemable: boolean;
  applicable_plan_codes: string[];
  display_name: string | null;
  headline: string | null;
  popup_enabled: boolean;
  popup_triggers: OfferPopupTrigger[];
}

export function hasShownOfferPopupThisSession(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(OFFER_POPUP_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function markOfferPopupShown(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(OFFER_POPUP_SESSION_KEY, "1");
  } catch {
    // ignore quota / private mode
  }
}

export function dispatchCreditsExhausted(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CREDITS_EXHAUSTED_EVENT));
}

/** Landing and marketing surfaces must not arm exit-intent popups. */
export function isOfferPopupPathBlocked(pathname: string | null | undefined): boolean {
  if (!pathname) return true;
  if (pathname === "/") return true;
  if (pathname === "/auth" || pathname.startsWith("/auth/")) return true;
  if (pathname.startsWith("/admin")) return true;
  if (pathname.startsWith("/legal")) return true;
  return false;
}

export function pickPopupOffer(
  offers: BillingPopupOffer[],
  trigger: OfferPopupTrigger,
): BillingPopupOffer | null {
  return (
    offers.find(
      (offer) =>
        offer.is_redeemable &&
        offer.popup_enabled &&
        offer.popup_triggers.includes(trigger),
    ) ?? null
  );
}

export function defaultCheckoutPlanCode(offer: BillingPopupOffer): string {
  const preferred = offer.applicable_plan_codes.find((code) => code === "monthly_pro");
  return preferred ?? offer.applicable_plan_codes[0] ?? "monthly_pro";
}

export function offerCountdownParts(
  expiresAt: string | null,
  nowMs: number = Date.now(),
): { days: number; hours: number; minutes: number; seconds: number } | null {
  if (!expiresAt) return null;
  const end = Date.parse(expiresAt);
  if (Number.isNaN(end)) return null;
  const remainingMs = Math.max(0, end - nowMs);
  const totalSeconds = Math.floor(remainingMs / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return { days, hours, minutes, seconds };
}

export function formatOfferCountdown(
  expiresAt: string | null,
  nowMs: number = Date.now(),
): string | null {
  const parts = offerCountdownParts(expiresAt, nowMs);
  if (!parts) return null;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (parts.days > 0) {
    return `${parts.days}d ${pad(parts.hours)}h ${pad(parts.minutes)}m`;
  }
  return `${pad(parts.hours)}:${pad(parts.minutes)}:${pad(parts.seconds)}`;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
