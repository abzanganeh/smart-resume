"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, Sparkles, Zap } from "lucide-react";
import {
  claimExhaustionTopUp,
  createCheckoutSessionByCode,
  getExhaustionPaywall,
  type BillingPlan,
  type ExhaustionPaywallResponse,
} from "@/lib/api";
import { clsx } from "clsx";

const FEATURE_LABELS: Record<string, string> = {
  resume_tailor: "Resume tailoring (ATS-optimised)",
  cover_letter: "Cover letter generation",
  fit_analysis: "Job fit analysis",
  job_search: "Job search (Hirebase)",
  master_resume: "Master resume profile",
  ats_guidance: "ATS score & guidance panel",
};

function formatCents(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

function planAllowances(plan: BillingPlan): string[] {
  const limits = plan.limits;
  if (!limits) return [];
  const period = plan.code === "weekly" ? "week" : plan.cycle === "yearly" ? "year" : "month";
  const lines = [
    `${limits.resumes_per_period} resumes & cover letters / ${period}`,
    `${limits.searches_per_period} job searches / ${period}`,
    `${limits.fit_analyses_per_period} fit analyses / ${period}`,
  ];
  lines.push(
    limits.whisper_uses_per_period === null
      ? "Whisper voice transcription (fair use)"
      : `${limits.whisper_uses_per_period} Whisper voice transcriptions / ${period}`,
  );
  return lines;
}

interface Props {
  token: string;
  /** Override the server headline when embedding in a specific flow. */
  contextMessage?: string;
  compact?: boolean;
  className?: string;
  onCreditsRefreshed?: () => void;
}

export function ExhaustionPaywall({
  token,
  contextMessage,
  compact = false,
  className,
  onCreditsRefreshed,
}: Props) {
  const [payload, setPayload] = useState<ExhaustionPaywallResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [busyTopUp, setBusyTopUp] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void getExhaustionPaywall(token)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Could not load upgrade options.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleSubscribe = useCallback(
    async (planCode: string) => {
      if (busyPlan) return;
      setBusyPlan(planCode);
      setLoadError(null);
      try {
        const origin = window.location.origin;
        const { url } = await createCheckoutSessionByCode(token, {
          code: planCode,
          success_url: `${origin}/billing?checkout=success`,
          cancel_url: `${origin}/billing?checkout=cancel`,
        });
        window.location.assign(url);
      } catch (err: unknown) {
        setLoadError(err instanceof Error ? err.message : "Checkout failed.");
        setBusyPlan(null);
      }
    },
    [busyPlan, token],
  );

  const handleTopUp = useCallback(async () => {
    if (busyTopUp) return;
    setBusyTopUp(true);
    setLoadError(null);
    try {
      await claimExhaustionTopUp(token);
      const refreshed = await getExhaustionPaywall(token);
      setPayload(refreshed);
      onCreditsRefreshed?.();
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : "Could not claim bonus credits.");
    } finally {
      setBusyTopUp(false);
    }
  }, [busyTopUp, onCreditsRefreshed, token]);

  if (loading) {
    return (
      <div
        className={clsx(
          "flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400",
          className,
        )}
      >
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading upgrade options…
      </div>
    );
  }

  if (!payload) {
    return (
      <div className={clsx("text-sm text-red-700 dark:text-red-400", className)}>
        {loadError ?? "Upgrade options unavailable."}
      </div>
    );
  }

  const headline = contextMessage ?? payload.headline;

  return (
    <div
      className={clsx(
        "rounded-2xl border border-amber-400/40 bg-gradient-to-b from-amber-50/80 to-white dark:from-amber-950/20 dark:to-slate-900/80 p-4 sm:p-5 space-y-4",
        className,
      )}
    >
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-semibold text-sm">
          <Sparkles className="w-4 h-4 shrink-0" />
          {headline}
        </div>
        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{payload.message}</p>
        {payload.credits_locked_until_verification && (
          <p className="text-xs text-amber-800 dark:text-amber-300">
            Verify your email in{" "}
            <Link href="/settings" className="underline font-medium">
              Settings
            </Link>{" "}
            to spend credits.
          </p>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Still free without credits
        </p>
        <ul className="grid gap-1.5 sm:grid-cols-3">
          {payload.free_still_available.map((item) => (
            <li key={item.id}>
              <Link
                href={item.path}
                className="block rounded-lg border border-slate-200 dark:border-slate-700 bg-white/70 dark:bg-slate-900/50 px-3 py-2 text-xs text-slate-700 dark:text-slate-300 hover:border-amber-400/50 transition-colors"
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      {payload.exhaustion_top_up_eligible && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/40 px-3 py-3">
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Need a few more tries? Claim a one-time bonus of {payload.exhaustion_top_up_amount}{" "}
            credits — once per account and device.
          </p>
          <button
            type="button"
            disabled={busyTopUp}
            onClick={() => void handleTopUp()}
            className="inline-flex items-center justify-center gap-2 shrink-0 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold px-3 py-2 hover:bg-amber-300 disabled:opacity-50"
          >
            {busyTopUp && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Claim bonus credits
          </button>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Upgrade to keep tailoring
          </p>
          {payload.yearly_savings_percent != null && payload.yearly_savings_percent > 0 && (
            <p className="text-xs text-emerald-700 dark:text-emerald-400 font-medium">
              Save {payload.yearly_savings_percent}% with annual Pro
            </p>
          )}
        </div>
        <div
          className={clsx(
            "grid gap-3",
            compact ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-1 md:grid-cols-3",
          )}
        >
          {payload.upgrade_plans.map((plan) => {
            const highlighted = plan.code === payload.highlight_plan_code;
            return (
              <div
                key={plan.code}
                className={clsx(
                  "relative flex flex-col rounded-xl border p-3 gap-3",
                  highlighted
                    ? "border-amber-400/60 bg-white dark:bg-slate-900 shadow-sm"
                    : "border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/60",
                )}
              >
                {highlighted && (
                  <span className="absolute -top-2.5 left-3 bg-amber-400 text-slate-900 text-[10px] font-bold px-2 py-0.5 rounded-full">
                    Most popular
                  </span>
                )}
                <div>
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {plan.display_name}
                  </h4>
                  <div className="flex items-end gap-1 mt-1">
                    <span className="text-xl font-bold text-slate-900 dark:text-white">
                      {formatCents(plan.amount_cents, payload.currency)}
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400 mb-0.5">
                      {plan.code === "weekly"
                        ? "/ week"
                        : plan.cycle === "yearly"
                          ? "/ year"
                          : "/ month"}
                    </span>
                  </div>
                </div>
                {!compact && (
                  <ul className="flex flex-col gap-1 flex-1">
                    {planAllowances(plan).slice(0, 3).map((line) => (
                      <li
                        key={line}
                        className="flex items-start gap-1.5 text-[11px] text-slate-700 dark:text-slate-300"
                      >
                        <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
                        {line}
                      </li>
                    ))}
                    {plan.features.slice(0, 2).map((feature) => (
                      <li
                        key={feature}
                        className="flex items-start gap-1.5 text-[11px] text-slate-600 dark:text-slate-400"
                      >
                        <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
                        {FEATURE_LABELS[feature] ?? feature}
                      </li>
                    ))}
                  </ul>
                )}
                <button
                  type="button"
                  disabled={busyPlan !== null}
                  onClick={() => void handleSubscribe(plan.code)}
                  className={clsx(
                    "w-full py-2 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5",
                    highlighted
                      ? "bg-amber-400 text-slate-900 hover:bg-amber-300 disabled:opacity-50"
                      : "bg-slate-200 dark:bg-slate-700 text-slate-900 dark:text-slate-100 hover:bg-slate-300 dark:hover:bg-slate-600 disabled:opacity-50",
                  )}
                >
                  {busyPlan === plan.code ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <>
                      <Zap className="w-3.5 h-3.5" />
                      Subscribe
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {loadError && (
        <p className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/20 border border-red-500/20 rounded-lg px-3 py-2">
          {loadError}
        </p>
      )}

      <p className="text-[11px] text-slate-500 dark:text-slate-400">
        Prefer to compare all tiers?{" "}
        <Link href="/billing" className="underline hover:no-underline text-amber-800 dark:text-amber-300">
          Open full billing page
        </Link>
      </p>
    </div>
  );
}
