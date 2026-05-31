"use client"

import { useEffect, useState, useCallback } from "react"
import { useSession } from "next-auth/react"
import {
  Check,
  CreditCard,
  Loader2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Sparkles,
  XCircle,
  Zap,
} from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import {
  getBillingPrices,
  getSubscriptionCurrent,
  createCheckoutSession,
  createPortalSession,
  cancelSubscription,
  resumeSubscription,
  pauseSubscription,
  unpauseSubscription,
  type BillingPlan,
  type BillingPricesResponse,
  type SubscriptionCurrentResponse,
} from "@/lib/api"
import { isSubscriptionActive, yearlyDiscountedAmount, yearlySavingsAmount } from "@/lib/billing"
import { clsx } from "clsx"

// ── Feature display labels ─────────────────────────────────────────────────

const FEATURE_LABELS: Record<string, string> = {
  resume_tailor: "Resume tailoring (ATS-optimised)",
  cover_letter: "Cover letter generation",
  fit_analysis: "Job fit analysis",
  job_search: "Job search (Hirebase)",
  master_resume: "Master resume profile",
  ats_guidance: "ATS score & guidance panel",
}

// ── Plan display config ────────────────────────────────────────────────────

const PLAN_ORDER = ["daily", "weekly", "monthly"]
const PLAN_HIGHLIGHT = "monthly"

// ── Helpers ────────────────────────────────────────────────────────────────

function formatCents(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  })
}

// ── Sub-components ─────────────────────────────────────────────────────────

interface PlanCardProps {
  plan: BillingPlan
  currency: string
  yearlyToggle: boolean
  isCurrentPlan: boolean
  isBusy: boolean
  onSubscribe: (stripePriceId: string, yearly: boolean) => void
}

function PlanCard({
  plan,
  currency,
  yearlyToggle,
  isCurrentPlan,
  isBusy,
  onSubscribe,
}: PlanCardProps) {
  const isMonthly = plan.cycle === "monthly"
  const showYearly = isMonthly && yearlyToggle
  const displayAmount = showYearly ? yearlyDiscountedAmount(plan.amount_cents) : plan.amount_cents
  const isHighlighted = plan.code === PLAN_HIGHLIGHT

  return (
    <div
      className={clsx(
        "relative flex flex-col rounded-2xl border p-6 gap-5 transition-shadow",
        isHighlighted
          ? "border-amber-400/60 bg-slate-900 shadow-[0_0_30px_-6px] shadow-amber-400/20"
          : "border-slate-700 bg-slate-900/60",
      )}
    >
      {isHighlighted && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-amber-400 text-slate-900 text-xs font-bold px-3 py-1 rounded-full">
            Most popular
          </span>
        </div>
      )}

      {plan.trial_days && plan.trial_days > 0 && (
        <div className="absolute top-4 right-4">
          <span className="bg-emerald-500/20 text-emerald-400 text-xs font-semibold px-2.5 py-1 rounded-full border border-emerald-500/30">
            {plan.trial_days}-day free trial
          </span>
        </div>
      )}

      <div>
        <h3 className="text-lg font-semibold text-slate-100">{plan.display_name}</h3>
        <div className="flex items-end gap-1.5 mt-2">
          <span className="text-3xl font-bold text-white">
            {formatCents(displayAmount, currency)}
          </span>
          <span className="text-slate-400 text-sm mb-1">
            {showYearly ? "/ year" : `/ ${plan.cycle}`}
          </span>
        </div>
        {showYearly && (
          <p className="text-emerald-400 text-xs mt-1 font-medium">
            Save 20% — {formatCents(yearlySavingsAmount(plan.amount_cents), currency)} off
          </p>
        )}
      </div>

      <ul className="flex flex-col gap-2 flex-1">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm text-slate-300">
            <Check className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
            {FEATURE_LABELS[f] ?? f}
          </li>
        ))}
      </ul>

      {isCurrentPlan ? (
        <div className="w-full py-2.5 text-center text-sm font-semibold text-amber-400 border border-amber-400/40 rounded-xl bg-amber-400/5">
          Current plan
        </div>
      ) : (
        <button
          onClick={() => onSubscribe(plan.stripe_price_id, showYearly)}
          disabled={isBusy}
          className={clsx(
            "w-full py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center justify-center gap-2",
            isHighlighted
              ? "bg-amber-400 text-slate-900 hover:bg-amber-300 disabled:opacity-50"
              : "bg-slate-700 text-slate-100 hover:bg-slate-600 disabled:opacity-50",
          )}
        >
          {isBusy ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <>
              <Zap className="w-4 h-4" />
              Subscribe
            </>
          )}
        </button>
      )}
    </div>
  )
}

interface UsageMeterProps {
  label: string
  used: number
  limit: number
}

function UsageMeter({ label, used, limit }: UsageMeterProps) {
  const pct = Math.min(100, (used / Math.max(limit, 1)) * 100)
  const color = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-400" : "bg-emerald-500"

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-slate-400">{label}</span>
        <span className="text-slate-300 font-medium tabular-nums">
          {used} / {limit}
        </span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={clsx("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function BillingPage() {
  const { session, status } = useRequireAuth("/billing")
  const { data: clientSession } = useSession()

  const [prices, setPrices] = useState<BillingPricesResponse | null>(null)
  const [current, setCurrent] = useState<SubscriptionCurrentResponse | null>(null)
  const [loadingPrices, setLoadingPrices] = useState(true)
  const [loadingCurrent, setLoadingCurrent] = useState(true)
  const [yearlyToggle, setYearlyToggle] = useState(false)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const token = clientSession?.backendAccessToken ?? session?.backendAccessToken

  const loadPrices = useCallback(async () => {
    setLoadingPrices(true)
    try {
      const data = await getBillingPrices(token ?? undefined)
      setPrices(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pricing")
    } finally {
      setLoadingPrices(false)
    }
  }, [token])

  const loadCurrent = useCallback(async () => {
    if (!token) return
    setLoadingCurrent(true)
    try {
      const data = await getSubscriptionCurrent(token)
      setCurrent(data)
    } catch {
      // Silently ignore — user may not have a subscription yet
      setCurrent({ subscription: null, credit_balance: 0 })
    } finally {
      setLoadingCurrent(false)
    }
  }, [token])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadPrices()
      void loadCurrent()
    }, 0)

    return () => {
      window.clearTimeout(timeout)
    }
  }, [loadPrices, loadCurrent])

  async function handleSubscribe(stripePriceId: string, yearly: boolean) {
    if (!token || busyAction) return
    setBusyAction("checkout")
    setError(null)
    try {
      const { checkout_url } = await createCheckoutSession(token, {
        stripe_price_id: stripePriceId,
        billing_cycle: yearly ? "yearly" : "recurring",
      })
      window.location.assign(checkout_url)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start checkout")
    } finally {
      setBusyAction(null)
    }
  }

  async function handlePortal() {
    if (!token || busyAction) return
    setBusyAction("portal")
    setError(null)
    try {
      const { portal_url } = await createPortalSession(token)
      window.location.assign(portal_url)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to open billing portal")
    } finally {
      setBusyAction(null)
    }
  }

  async function handleCancel() {
    if (!token || busyAction) return
    setBusyAction("cancel")
    setError(null)
    try {
      await cancelSubscription(token)
      await loadCurrent()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to cancel subscription")
    } finally {
      setBusyAction(null)
    }
  }

  async function handleResume() {
    if (!token || busyAction) return
    setBusyAction("resume")
    setError(null)
    try {
      await resumeSubscription(token)
      await loadCurrent()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resume subscription")
    } finally {
      setBusyAction(null)
    }
  }

  async function handlePause() {
    if (!token || busyAction) return
    setBusyAction("pause")
    setError(null)
    try {
      await pauseSubscription(token)
      await loadCurrent()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to pause subscription")
    } finally {
      setBusyAction(null)
    }
  }

  async function handleUnpause() {
    if (!token || busyAction) return
    setBusyAction("unpause")
    setError(null)
    try {
      await unpauseSubscription(token)
      await loadCurrent()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resume subscription")
    } finally {
      setBusyAction(null)
    }
  }

  if (status === "loading" || !session) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    )
  }

  const sub = current?.subscription
  const isSubscribed = !!sub && isSubscriptionActive(sub.status)
  const isAnyActionBusy = busyAction !== null
  const orderedPlans = prices
    ? [...prices.plans].sort(
        (a, b) => PLAN_ORDER.indexOf(a.cycle) - PLAN_ORDER.indexOf(b.cycle),
      )
    : []

  return (
    <main className="max-w-5xl mx-auto px-4 py-10 space-y-10">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-amber-400" />
          Billing &amp; Plans
        </h1>
        <p className="text-slate-400 text-sm">
          Manage your subscription, usage, and payment details.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-950/50 border border-red-800 text-red-300 text-sm px-4 py-3 rounded-xl flex items-center gap-2">
          <XCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Current subscription card */}
      {isSubscribed && sub && (
        <section className="bg-slate-900 border border-slate-700 rounded-2xl p-6 space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wider font-medium">
                Current plan
              </p>
              <h2 className="text-xl font-bold text-white capitalize mt-0.5">
                {sub.plan}{" "}
                {sub.billing_cycle === "yearly" && (
                  <span className="text-sm font-normal text-amber-400">(yearly)</span>
                )}
              </h2>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={sub.status} />
                {sub.cancel_at_period_end && (
                  <span className="text-xs text-amber-400">
                    Cancels {formatDate(sub.period_end)}
                  </span>
                )}
              </div>
            </div>
            <div className="text-right text-sm text-slate-400">
              {sub.status === "trialing" && sub.trial_ends_at ? (
                <p>
                  Trial ends{" "}
                  <span className="text-slate-200 font-medium">
                    {formatDate(sub.trial_ends_at)}
                  </span>
                </p>
              ) : (
                <p>
                  Renews{" "}
                  <span className="text-slate-200 font-medium">
                    {formatDate(sub.period_end)}
                  </span>
                </p>
              )}
              <p className="text-xs mt-0.5">
                Period: {formatDate(sub.period_start)} — {formatDate(sub.period_end)}
              </p>
            </div>
          </div>

          {/* Usage meters */}
          <div className="space-y-3 pt-2 border-t border-slate-800">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              This period
            </p>
            <UsageMeter
              label="Resumes built"
              used={sub.resumes_used}
              limit={sub.resumes_limit}
            />
            <UsageMeter
              label="Job searches"
              used={sub.searches_used}
              limit={sub.searches_limit}
            />
          </div>

          {/* Management CTAs */}
          <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
            <ActionButton
              label="Billing portal"
              icon={<CreditCard className="w-4 h-4" />}
              busy={busyAction === "portal"}
              onClick={handlePortal}
              variant="primary"
              disabled={isAnyActionBusy}
            />

            {sub.paused_at ? (
              <ActionButton
                label="Resume plan"
                icon={<PlayCircle className="w-4 h-4" />}
                busy={busyAction === "unpause"}
                onClick={handleUnpause}
                disabled={isAnyActionBusy}
              />
            ) : (
              <ActionButton
                label="Pause plan"
                icon={<PauseCircle className="w-4 h-4" />}
                busy={busyAction === "pause"}
                onClick={handlePause}
                disabled={isAnyActionBusy}
              />
            )}

            {sub.cancel_at_period_end ? (
              <ActionButton
                label="Don't cancel"
                icon={<RefreshCw className="w-4 h-4" />}
                busy={busyAction === "resume"}
                onClick={handleResume}
                disabled={isAnyActionBusy}
              />
            ) : (
              <ActionButton
                label="Cancel plan"
                icon={<XCircle className="w-4 h-4" />}
                busy={busyAction === "cancel"}
                onClick={handleCancel}
                variant="danger"
                disabled={isAnyActionBusy}
              />
            )}
          </div>
        </section>
      )}

      {/* Free credits summary (no subscription) */}
      {!isSubscribed && !loadingCurrent && current && (
        <section className="bg-slate-900 border border-slate-700 rounded-2xl p-5 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-slate-400">Free credits remaining</p>
            <p className="text-2xl font-bold text-amber-400">
              {current.credit_balance}{" "}
              <span className="text-sm font-normal text-slate-400">
                credit{current.credit_balance === 1 ? "" : "s"} left
              </span>
            </p>
          </div>
          <p className="text-xs text-slate-500 max-w-[200px] text-right">
            Subscribe to a plan for unlimited access and job search.
          </p>
        </section>
      )}

      {/* Plan selection */}
      <section className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-white">
            {isSubscribed ? "Change plan" : "Choose a plan"}
          </h2>

          {/* Yearly toggle */}
          {orderedPlans.some((p) => p.cycle === "monthly") && (
            <button
              onClick={() => setYearlyToggle((v) => !v)}
              className={clsx(
                "flex items-center gap-2 text-sm px-4 py-2 rounded-xl border transition-colors",
                yearlyToggle
                  ? "bg-amber-400/10 border-amber-400/40 text-amber-400"
                  : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200",
              )}
            >
              <span
                className={clsx(
                  "w-8 h-4 rounded-full relative transition-colors",
                  yearlyToggle ? "bg-amber-400" : "bg-slate-600",
                )}
              >
                <span
                  className={clsx(
                    "absolute top-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform",
                    yearlyToggle ? "translate-x-4 left-0.5" : "left-0.5",
                  )}
                />
              </span>
              Yearly billing (−20%)
            </button>
          )}
        </div>

        {loadingPrices ? (
          <div className="grid sm:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-72 bg-slate-800 rounded-2xl animate-pulse"
              />
            ))}
          </div>
        ) : (
          <div className="grid sm:grid-cols-3 gap-4">
            {orderedPlans.map((plan) => (
              <PlanCard
                key={plan.code}
                plan={plan}
                currency={prices?.currency ?? "USD"}
                yearlyToggle={yearlyToggle}
                isCurrentPlan={isSubscribed && sub?.plan === plan.code}
                isBusy={isAnyActionBusy}
                onSubscribe={handleSubscribe}
              />
            ))}
          </div>
        )}
        {!loadingPrices && orderedPlans.length === 0 && (
          <div className="bg-slate-900 border border-slate-700 rounded-2xl px-5 py-6 text-sm text-slate-300 flex flex-wrap items-center justify-between gap-3">
            <p>
              Pricing is temporarily unavailable. Please retry in a moment.
            </p>
            <button
              type="button"
              onClick={() => {
                setError(null)
                void loadPrices()
                if (token) void loadCurrent()
              }}
              className="bg-slate-800 text-slate-100 px-3 py-2 rounded-lg border border-slate-700 hover:bg-slate-700 transition-colors"
            >
              Retry
            </button>
          </div>
        )}
      </section>
    </main>
  )
}

// ── Shared sub-components ──────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    active: { label: "Active", className: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
    trialing: { label: "Trial", className: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
    grace: { label: "Payment failed", className: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
    paused: { label: "Paused", className: "bg-slate-600/40 text-slate-400 border-slate-600/50" },
    cancel_at_period_end: {
      label: "Cancels at period end",
      className: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    },
    cancelled: { label: "Cancelled", className: "bg-red-500/20 text-red-400 border-red-500/30" },
    expired: { label: "Expired", className: "bg-red-500/20 text-red-400 border-red-500/30" },
  }
  const cfg = map[status] ?? { label: status, className: "bg-slate-700 text-slate-400 border-slate-600" }
  return (
    <span className={clsx("text-xs font-semibold px-2.5 py-0.5 rounded-full border", cfg.className)}>
      {cfg.label}
    </span>
  )
}

interface ActionButtonProps {
  label: string
  icon: React.ReactNode
  busy: boolean
  disabled?: boolean
  onClick: () => void
  variant?: "primary" | "default" | "danger"
}

function ActionButton({
  label,
  icon,
  busy,
  disabled = false,
  onClick,
  variant = "default",
}: ActionButtonProps) {
  const cls = {
    primary: "bg-amber-400 text-slate-900 hover:bg-amber-300",
    default: "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700",
    danger: "bg-red-950/60 text-red-400 hover:bg-red-950 border border-red-800/50",
  }[variant]

  return (
    <button
      onClick={onClick}
      disabled={busy || disabled}
      className={clsx(
        "flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl transition-colors disabled:opacity-50",
        cls,
      )}
    >
      {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : icon}
      {label}
    </button>
  )
}
