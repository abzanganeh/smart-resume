"use client";

import { useEffect, useState } from "react";
import {
  FREE_TIER_STARTING_CREDITS,
  fetchFreeTierStartingCredits,
  formatSignupCreditsCopy,
} from "@/lib/freeTier";

type Props = {
  className?: string;
  suffix?: string;
};

export function FreeTierSignupCredits({ className, suffix = " · No credit card" }: Props) {
  const [credits, setCredits] = useState(FREE_TIER_STARTING_CREDITS);

  useEffect(() => {
    let active = true;
    void fetchFreeTierStartingCredits().then((value) => {
      if (active) setCredits(value);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <p className={className}>
      {formatSignupCreditsCopy(credits)}
      {suffix}
    </p>
  );
}
