"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, X, Zap } from "lucide-react";
import { createCheckoutSessionByCode } from "@/lib/api";
import {
  defaultCheckoutPlanCode,
  markOfferPopupShown,
  type BillingPopupOffer,
  type OfferPopupTrigger,
} from "@/lib/offerPopup";
import { OfferCountdown } from "@/components/billing/OfferCountdown";
import { clsx } from "clsx";

function offerTitle(offer: BillingPopupOffer): string {
  return offer.headline ?? offer.display_name ?? "Limited-time upgrade offer";
}

interface Props {
  offer: BillingPopupOffer;
  trigger: OfferPopupTrigger;
  token: string;
  onDismiss: () => void;
}

export function OfferPopup({ offer, trigger, token, onDismiss }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        markOfferPopupShown();
        onDismiss();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onDismiss]);

  const handleDismiss = useCallback(() => {
    markOfferPopupShown();
    onDismiss();
  }, [onDismiss]);

  const handleClaim = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const planCode = defaultCheckoutPlanCode(offer);
      const origin = window.location.origin;
      const { url } = await createCheckoutSessionByCode(token, {
        code: planCode,
        success_url: `${origin}/billing?checkout=success&offer=${encodeURIComponent(offer.code)}`,
        cancel_url: `${origin}/billing?checkout=cancel`,
        promo_code: offer.code,
      });
      markOfferPopupShown();
      window.location.assign(url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start checkout.");
      setBusy(false);
    }
  }, [busy, offer, token]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-4 bg-slate-900/50"
      role="presentation"
      onClick={handleDismiss}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="offer-popup-title"
        aria-describedby="offer-popup-desc"
        className={clsx(
          "relative w-full max-w-md rounded-2xl border border-amber-400/40 bg-white dark:bg-slate-900 shadow-xl p-6 space-y-4",
          !reducedMotion &&
            "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-4 motion-safe:duration-300",
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <button
          ref={closeRef}
          type="button"
          onClick={handleDismiss}
          className="absolute top-3 right-3 rounded-lg p-1.5 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          aria-label="Dismiss offer"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="space-y-2 pr-8">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
            {trigger === "post_exhaustion" ? "Before you go" : "Limited-time offer"}
          </p>
          <h2 id="offer-popup-title" className="text-xl font-bold text-slate-900 dark:text-white">
            {offerTitle(offer)}
          </h2>
          {offer.display_name && offer.headline && (
            <p className="text-sm text-slate-600 dark:text-slate-400">{offer.display_name}</p>
          )}
          <p
            id="offer-popup-desc"
            className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed"
          >
            Claim your discount at checkout — the reduced price is applied automatically when you
            subscribe.
          </p>
          <OfferCountdown expiresAt={offer.expires_at} />
        </div>

        {error && (
          <p className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/20 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex flex-col sm:flex-row gap-2 pt-1">
          <button
            type="button"
            onClick={() => void handleClaim()}
            disabled={busy}
            className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-amber-400 text-slate-900 font-semibold px-4 py-2.5 hover:bg-amber-300 disabled:opacity-50 transition-colors"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Zap className="w-4 h-4" />
                Claim offer
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleDismiss}
            disabled={busy}
            className="flex-1 rounded-xl border border-slate-300 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-300 px-4 py-2.5 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
