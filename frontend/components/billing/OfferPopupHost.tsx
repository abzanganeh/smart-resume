"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { getPopupOffers } from "@/lib/api";
import { useEntitlement } from "@/hooks/useEntitlement";
import { useExitIntent } from "@/hooks/useExitIntent";
import {
  CREDITS_EXHAUSTED_EVENT,
  hasShownOfferPopupThisSession,
  isOfferPopupPathBlocked,
  markOfferPopupShown,
  pickPopupOffer,
  type BillingPopupOffer,
  type OfferPopupTrigger,
} from "@/lib/offerPopup";
import { OfferPopup } from "@/components/billing/OfferPopup";

export function OfferPopupHost() {
  const pathname = usePathname();
  const { data: session, status } = useSession();
  const token = session?.backendAccessToken;
  const entitlement = useEntitlement();
  const [offers, setOffers] = useState<BillingPopupOffer[]>([]);
  const [activeOffer, setActiveOffer] = useState<BillingPopupOffer | null>(null);
  const [activeTrigger, setActiveTrigger] = useState<OfferPopupTrigger | null>(null);
  const prevBalanceRef = useRef<number | null>(null);

  const pathBlocked = isOfferPopupPathBlocked(pathname);
  const eligibleUser =
    status === "authenticated" &&
    !!token &&
    entitlement.isSubscribed === false &&
    !entitlement.loading;

  useEffect(() => {
    if (!eligibleUser || !token) {
      setOffers([]);
      return;
    }
    let cancelled = false;
    void getPopupOffers(token)
      .then((payload) => {
        if (!cancelled) setOffers(payload.offers);
      })
      .catch(() => {
        if (!cancelled) setOffers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [eligibleUser, token]);

  const tryShow = useCallback(
    (trigger: OfferPopupTrigger) => {
      if (!eligibleUser || pathBlocked || hasShownOfferPopupThisSession()) return;
      if (activeOffer) return;
      const offer = pickPopupOffer(offers, trigger);
      if (!offer) return;
      setActiveTrigger(trigger);
      setActiveOffer(offer);
    },
    [activeOffer, eligibleUser, offers, pathBlocked],
  );

  useExitIntent(() => tryShow("exit_intent"), eligibleUser && !pathBlocked && offers.length > 0);

  useEffect(() => {
    const onCreditsExhausted = () => tryShow("post_exhaustion");
    window.addEventListener(CREDITS_EXHAUSTED_EVENT, onCreditsExhausted);
    return () => window.removeEventListener(CREDITS_EXHAUSTED_EVENT, onCreditsExhausted);
  }, [tryShow]);

  useEffect(() => {
    if (entitlement.creditBalance === null || entitlement.loading) return;
    if (
      prevBalanceRef.current !== null &&
      prevBalanceRef.current > 0 &&
      entitlement.creditBalance === 0
    ) {
      tryShow("post_exhaustion");
    }
    prevBalanceRef.current = entitlement.creditBalance;
  }, [entitlement.creditBalance, entitlement.loading, tryShow]);

  if (!activeOffer || !activeTrigger || !token) return null;

  return (
    <OfferPopup
      offer={activeOffer}
      trigger={activeTrigger}
      token={token}
      onDismiss={() => {
        markOfferPopupShown();
        setActiveOffer(null);
        setActiveTrigger(null);
      }}
    />
  );
}
