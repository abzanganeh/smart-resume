"use client";

import { useEffect, useState } from "react";
import { formatOfferCountdown, prefersReducedMotion } from "@/lib/offerPopup";
import { clsx } from "clsx";

interface Props {
  expiresAt: string | null;
  className?: string;
}

/** Live countdown driven by the server-provided offer deadline. */
export function OfferCountdown({ expiresAt, className }: Props) {
  const [label, setLabel] = useState<string | null>(() =>
    formatOfferCountdown(expiresAt),
  );
  const reducedMotion = prefersReducedMotion();

  useEffect(() => {
    if (!expiresAt) {
      setLabel(null);
      return;
    }
    setLabel(formatOfferCountdown(expiresAt));
    if (reducedMotion) return;

    const id = window.setInterval(() => {
      setLabel(formatOfferCountdown(expiresAt));
    }, 1000);
    return () => window.clearInterval(id);
  }, [expiresAt, reducedMotion]);

  if (!expiresAt || !label) return null;

  return (
    <p
      className={clsx(
        "text-xs font-medium tabular-nums text-amber-800 dark:text-amber-300",
        className,
      )}
      aria-live="polite"
    >
      Offer ends in {label}
    </p>
  );
}
