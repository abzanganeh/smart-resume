"use client"

import { useMemo } from "react"
import { clsx } from "clsx"
import { Sparkles, Zap, Crown, Lock, AlertTriangle } from "lucide-react"
import type {
  LLMTier,
  LLMUpgradeCheckoutCode,
  LLMUpgradeStatus,
} from "@/lib/api"

// ── Pricing snapshot ────────────────────────────────────────────────────────
//
// The exact dollar amounts come from SYSTEM_DESIGN_PHASE_2 §18.3 / §18.9
// (single source of truth).  They are duplicated here only for the
// pricing copy on the selector — the backend always reads the live price
// id from PlanConfig.  Keep these strings aligned with the design doc.
//

export const LLM_TIER_PRICING = {
  standard: {
    label: "Standard",
    model: "Gemini 2.5 Flash-Lite",
    perResumeCopy: "Included with your plan",
    monthlyCopy: "Included",
    yearlyCopy: "Included",
  },
  better: {
    label: "Better",
    model: "Gemini 2.5 Flash",
    perResumeCopy: "+$0.898 / resume ($4.49 for 5)",
    monthlyCopy: "+$4.99 / month",
    yearlyCopy: "+$47.90 / year",
  },
  best: {
    label: "Best",
    model: "Claude Sonnet 4.6",
    perResumeCopy: "+$2.99 / resume",
    monthlyCopy: "+$12.99 / month",
    yearlyCopy: "+$124.99 / year",
  },
} as const

const TIER_ORDER: LLMTier[] = ["standard", "better", "best"]


// ── Pure helpers (exported for unit-tests) ─────────────────────────────────


export interface TierVisualState {
  tier: LLMTier
  /** ``true`` when the user is allowed to run Phase 3 with this tier
   *  *without* opening the Purchase modal first.  Standard is always
   *  runnable; Better is runnable when the user has any Better
   *  entitlement (subscription or credit balance > 0); Best is runnable
   *  when the user has an active Best subscription AND the soft cap
   *  hasn't fired yet. */
  runnable: boolean
  /** ``true`` when the option is greyed-out because the soft cap has
   *  fired this period.  Only meaningful for the Best option. */
  softCapHit: boolean
  /** Optional badge copy ("5 credits remaining", "Quota reached…"). */
  badge?: string
}


export function deriveTierVisualState(
  tier: LLMTier,
  status: LLMUpgradeStatus | null,
): TierVisualState {
  if (tier === "standard") {
    return { tier, runnable: true, softCapHit: false }
  }
  if (status === null) {
    return { tier, runnable: false, softCapHit: false }
  }
  if (tier === "better") {
    const hasSubscription = status.better_subscription_active
    const hasCredits = status.better_credits_balance > 0
    return {
      tier,
      runnable: hasSubscription || hasCredits,
      softCapHit: false,
      badge: hasCredits
        ? `${status.better_credits_balance} credits remaining`
        : hasSubscription
          ? "Subscription active"
          : undefined,
    }
  }
  // tier === "best"
  if (status.best_soft_cap_hit) {
    return {
      tier,
      runnable: false,
      softCapHit: true,
      badge: "Quota reached — using Standard",
    }
  }
  if (status.best_subscription_active) {
    const remaining = Math.max(
      0,
      status.upgraded_resumes_limit - status.upgraded_resumes_used,
    )
    return {
      tier,
      runnable: true,
      softCapHit: false,
      badge: `${remaining} of ${status.upgraded_resumes_limit} this period`,
    }
  }
  return { tier, runnable: false, softCapHit: false }
}


export interface PurchaseOptionView {
  /** Canonical ``code`` accepted by ``/api/subscriptions/llm-upgrade/checkout``. */
  code: LLMUpgradeCheckoutCode
  label: string
  copy: string
}


/**
 * Build the purchase-modal options that should be shown for a given tier
 * and the user's base billing cycle.
 *
 * §7.7 rule: yearly add-ons require a yearly base subscription.  When
 * the user is on a monthly base we **omit** the yearly option entirely
 * so the UI never lets them request a 409 from the backend.
 */
export function purchaseOptionsForTier(
  tier: Exclude<LLMTier, "standard">,
  baseBillingCycle: LLMUpgradeStatus["base_billing_cycle"],
): PurchaseOptionView[] {
  const showYearly = baseBillingCycle === "yearly"
  if (tier === "better") {
    const options: PurchaseOptionView[] = [
      {
        code: "better_5pack",
        label: "Buy 5-pack",
        copy: LLM_TIER_PRICING.better.perResumeCopy,
      },
      {
        code: "better_monthly",
        label: "Subscribe monthly",
        copy: LLM_TIER_PRICING.better.monthlyCopy,
      },
    ]
    if (showYearly) {
      options.push({
        code: "better_yearly",
        label: "Subscribe yearly (−20%)",
        copy: LLM_TIER_PRICING.better.yearlyCopy,
      })
    }
    return options
  }
  // tier === "best"
  const options: PurchaseOptionView[] = [
    {
      code: "best_per_resume",
      label: "Buy 1 resume",
      copy: LLM_TIER_PRICING.best.perResumeCopy,
    },
    {
      code: "best_monthly",
      label: "Subscribe monthly",
      copy: LLM_TIER_PRICING.best.monthlyCopy,
    },
  ]
  if (showYearly) {
    options.push({
      code: "best_yearly",
      label: "Subscribe yearly (−20%)",
      copy: LLM_TIER_PRICING.best.yearlyCopy,
    })
  }
  return options
}


// ── React component ────────────────────────────────────────────────────────


interface LLMTierSelectorProps {
  /** Currently-selected tier.  Defaults to ``"standard"``. */
  value: LLMTier
  /** Live entitlement snapshot from ``GET /api/subscriptions/llm-upgrade/status``. */
  status: LLMUpgradeStatus | null
  /** Disable the whole selector while a Phase 3 run is streaming. */
  disabled?: boolean
  onChange: (tier: LLMTier) => void
  /** Open the purchase modal for an upgrade tier (the user clicked an
   *  un-runnable Better/Best option). */
  onRequestPurchase: (tier: Exclude<LLMTier, "standard">) => void
}


const TIER_ICON: Record<LLMTier, typeof Sparkles> = {
  standard: Sparkles,
  better: Zap,
  best: Crown,
}


export function LLMTierSelector({
  value,
  status,
  disabled,
  onChange,
  onRequestPurchase,
}: LLMTierSelectorProps) {
  const visuals = useMemo(
    () => TIER_ORDER.map((tier) => deriveTierVisualState(tier, status)),
    [status],
  )

  const softCapBanner = status?.best_soft_cap_hit ? (
    <div className="mb-3 flex items-center gap-2 text-amber-300 text-xs bg-amber-400/10 border border-amber-400/30 rounded-md px-3 py-2">
      <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
      <span>
        Best LLM quota reached for this period — Phase 3 runs use the
        Standard tier until your subscription renews.
      </span>
    </div>
  ) : null

  return (
    <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-200">LLM Model</h2>
        <span className="text-[11px] uppercase tracking-wide text-slate-500">
          Phase 3 only
        </span>
      </div>
      {softCapBanner}
      <div
        role="radiogroup"
        aria-label="Phase 3 LLM tier"
        className="grid grid-cols-1 sm:grid-cols-3 gap-2"
      >
        {visuals.map((v) => {
          const Icon = TIER_ICON[v.tier]
          const pricing = LLM_TIER_PRICING[v.tier]
          const selected = v.tier === value
          const greyedOut = v.softCapHit || disabled
          const badgeColor =
            v.tier === "best"
              ? "bg-fuchsia-400/15 text-fuchsia-300"
              : v.tier === "better"
                ? "bg-emerald-400/15 text-emerald-300"
                : "bg-slate-700/40 text-slate-300"
          const handleClick = () => {
            if (greyedOut) return
            if (v.runnable) {
              onChange(v.tier)
              return
            }
            if (v.tier !== "standard") {
              onRequestPurchase(v.tier)
            }
          }
          return (
            <button
              key={v.tier}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-disabled={greyedOut || undefined}
              data-tier={v.tier}
              data-runnable={v.runnable ? "true" : "false"}
              data-soft-cap-hit={v.softCapHit ? "true" : "false"}
              disabled={greyedOut}
              onClick={handleClick}
              className={clsx(
                "relative flex flex-col gap-1.5 text-left rounded-lg border px-3 py-2.5 transition-colors",
                selected
                  ? "border-amber-400/70 bg-amber-400/10"
                  : "border-slate-700 hover:border-slate-500 bg-slate-900/60",
                greyedOut && "opacity-50 cursor-not-allowed",
              )}
            >
              <div className="flex items-center gap-2">
                <Icon className="w-3.5 h-3.5 text-amber-300" />
                <span className="text-sm font-semibold text-slate-100">
                  {pricing.label}
                </span>
                {!v.runnable && v.tier !== "standard" && !v.softCapHit && (
                  <Lock className="w-3 h-3 text-slate-500 ml-auto" />
                )}
              </div>
              <div className="text-[11px] text-slate-400">{pricing.model}</div>
              <div className="text-[11px] text-slate-300">
                {pricing.perResumeCopy}
              </div>
              {v.badge && (
                <div
                  className={clsx(
                    "text-[10px] font-medium rounded px-1.5 py-0.5 self-start mt-1",
                    badgeColor,
                  )}
                >
                  {v.badge}
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}


// ── Purchase modal ─────────────────────────────────────────────────────────


interface LLMUpgradePurchaseModalProps {
  open: boolean
  tier: Exclude<LLMTier, "standard"> | null
  status: LLMUpgradeStatus | null
  onClose: () => void
  onCheckout: (code: LLMUpgradeCheckoutCode) => Promise<void> | void
  busyCode?: LLMUpgradeCheckoutCode | null
}


export function LLMUpgradePurchaseModal({
  open,
  tier,
  status,
  onClose,
  onCheckout,
  busyCode,
}: LLMUpgradePurchaseModalProps) {
  if (!open || tier === null) return null
  const options = purchaseOptionsForTier(
    tier,
    status?.base_billing_cycle ?? null,
  )
  const heading =
    tier === "better" ? "Upgrade to Better" : "Upgrade to Best"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              {heading}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Choose how you&apos;d like to access the {LLM_TIER_PRICING[tier].model} tier.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-sm"
          >
            Close
          </button>
        </div>
        {status?.base_billing_cycle === "recurring" && (
          <p className="text-[11px] text-slate-500 mb-3">
            Yearly add-ons are only available on a yearly base subscription.
          </p>
        )}
        <div className="flex flex-col gap-2">
          {options.map((opt) => (
            <button
              key={opt.code}
              type="button"
              data-code={opt.code}
              disabled={busyCode === opt.code}
              onClick={() => void onCheckout(opt.code)}
              className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-800 px-3 py-2 text-sm disabled:opacity-50"
            >
              <span className="text-slate-100 font-medium">{opt.label}</span>
              <span className="text-slate-400 text-xs">{opt.copy}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}


export default LLMTierSelector
