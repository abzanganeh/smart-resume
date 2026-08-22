"use client"

import { useEffect, useState, useTransition } from "react"
import { useRouter } from "next/navigation"
import { Copy, Loader2, Plus, Tag } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  createAdminPromoCode,
  getAdminFreeGrant,
  listAdminPromoCodes,
  patchAdminFreeGrant,
  patchAdminPromoCode,
} from "@/lib/admin/api"
import { generatePromoCode } from "@/lib/admin/promoCode"
import type { PromoCode } from "@/lib/admin/types"

const inputCls =
  "bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-amber-500/60"

export default function AdminPromoPage() {
  const router = useRouter()
  const { token } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freeGrant, setFreeGrant] = useState(3)
  const [grantDraft, setGrantDraft] = useState("3")
  const [promos, setPromos] = useState<PromoCode[]>([])
  const [discountOffers, setDiscountOffers] = useState<PromoCode[]>([])
  const [campaignCode, setCampaignCode] = useState("")
  const [campaignAmount, setCampaignAmount] = useState("5")
  const [campaignMax, setCampaignMax] = useState("")
  const [offerCode, setOfferCode] = useState("")
  const [offerStripePromoId, setOfferStripePromoId] = useState("")
  const [offerDisplayName, setOfferDisplayName] = useState("")
  const [offerPlans, setOfferPlans] = useState("monthly_pro,yearly_pro")
  const [offerMax, setOfferMax] = useState("")
  const [offerExpiresAt, setOfferExpiresAt] = useState("")
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    if (!token) return
    void loadData()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [grant, codes] = await Promise.all([
        getAdminFreeGrant(token!),
        listAdminPromoCodes(token!, true),
      ])
      setFreeGrant(grant.amount)
      setGrantDraft(String(grant.amount))
      setPromos(codes.filter((p) => p.restricted_user_id == null && p.grant_type === "extra_credits"))
      setDiscountOffers(
        codes.filter((p) => p.restricted_user_id == null && p.grant_type === "price_discount"),
      )
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load promo settings"
      if (msg === "admin_setup_incomplete") {
        router.replace("/admin/auth?reason=setup_password")
        return
      }
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  function runAction(fn: () => Promise<void>) {
    startTransition(async () => {
      try {
        await fn()
      } catch (e) {
        setError(e instanceof Error ? e.message : "Action failed")
      }
    })
  }

  if (!token) {
    return (
      <p className="text-slate-400 text-sm">Sign in at /admin/auth to manage promo settings.</p>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  return (
    <div className="space-y-8 max-w-5xl">
      <div>
        <h1 className="text-2xl font-semibold text-white">Promo & credits</h1>
        <p className="text-sm text-slate-400 mt-1">
          Global signup credits and campaign coupon codes.
        </p>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <h2 className="text-lg font-medium text-white">Free plan starting credits</h2>
        <p className="text-sm text-slate-400">
          New free accounts receive this many credits. Existing balances do not change.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1">
            <span className="text-xs text-slate-500">Credits at signup</span>
            <input
              type="number"
              min={0}
              value={grantDraft}
              onChange={(e) => setGrantDraft(e.target.value)}
              className={inputCls + " w-28"}
            />
          </label>
          <button
            disabled={isPending || grantDraft === String(freeGrant)}
            onClick={() =>
              runAction(async () => {
                const amount = parseInt(grantDraft, 10)
                if (Number.isNaN(amount) || amount < 0) return
                const res = await patchAdminFreeGrant(token, amount)
                showAuditToast(res.audit_log_id)
                setFreeGrant(res.free_grant.amount)
                setGrantDraft(String(res.free_grant.amount))
              })
            }
            className="bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm px-4 py-2 rounded-lg transition-colors"
          >
            Save
          </button>
          <p className="text-xs text-slate-500">Current: {freeGrant}</p>
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <h2 className="text-lg font-medium text-white">Campaign coupons</h2>
        <p className="text-sm text-slate-400">
          Anyone signed in can redeem these codes once per account.
        </p>
        <div className="grid sm:grid-cols-3 gap-3">
          <input
            type="text"
            value={campaignCode}
            onChange={(e) => setCampaignCode(e.target.value.toUpperCase())}
            placeholder="Code (optional — auto-generated)"
            className={inputCls}
          />
          <input
            type="number"
            min={1}
            value={campaignAmount}
            onChange={(e) => setCampaignAmount(e.target.value)}
            placeholder="Credits"
            className={inputCls}
          />
          <input
            type="number"
            min={1}
            value={campaignMax}
            onChange={(e) => setCampaignMax(e.target.value)}
            placeholder="Max redemptions (optional)"
            className={inputCls}
          />
        </div>
        <button
          disabled={isPending || !campaignAmount}
          onClick={() =>
            runAction(async () => {
              const amount = parseInt(campaignAmount, 10)
              if (Number.isNaN(amount) || amount < 1) return
              const code = campaignCode.trim() || generatePromoCode()
              const res = await createAdminPromoCode(token, {
                code,
                grant_type: "extra_credits",
                payload: { amount, credit_kind: "free" },
                max_redemptions: campaignMax ? parseInt(campaignMax, 10) : null,
              })
              showAuditToast(res.audit_log_id)
              setPromos((prev) => [res.promo_code, ...prev])
              setCampaignCode("")
              setCampaignMax("")
            })
          }
          className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create campaign code
        </button>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <th className="py-2 pr-4">Code</th>
                <th className="py-2 pr-4">Credits</th>
                <th className="py-2 pr-4">Redemptions</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2">&nbsp;</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {promos.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-slate-500">
                    No campaign codes yet.
                  </td>
                </tr>
              )}
              {promos.map((promo) => (
                <tr key={promo.id}>
                  <td className="py-3 pr-4 font-mono text-white">{promo.code}</td>
                  <td className="py-3 pr-4 text-slate-300">
                    {String((promo.payload as { amount?: number }).amount ?? "—")}
                  </td>
                  <td className="py-3 pr-4 text-slate-300">
                    {promo.redemption_count}
                    {promo.max_redemptions != null ? ` / ${promo.max_redemptions}` : ""}
                  </td>
                  <td className="py-3 pr-4">
                    <span
                      className={clsx(
                        "text-xs px-2 py-0.5 rounded-full border",
                        promo.is_active
                          ? "border-emerald-700/40 text-emerald-300 bg-emerald-900/20"
                          : "border-slate-700 text-slate-400 bg-slate-800/50",
                      )}
                    >
                      {promo.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="py-3 text-right space-x-2">
                    <button
                      type="button"
                      onClick={() => void navigator.clipboard.writeText(promo.code)}
                      className="text-slate-400 hover:text-white"
                      title="Copy code"
                    >
                      <Copy className="w-4 h-4 inline" />
                    </button>
                    {promo.is_active && (
                      <button
                        disabled={isPending}
                        onClick={() =>
                          runAction(async () => {
                            const res = await patchAdminPromoCode(token, promo.id, {
                              is_active: false,
                            })
                            showAuditToast(res.audit_log_id)
                            setPromos((prev) =>
                              prev.map((p) =>
                                p.id === promo.id ? res.promo_code : p,
                              ),
                            )
                          })
                        }
                        className="text-xs text-red-300 hover:text-red-200"
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <h2 className="text-lg font-medium text-white">Checkout discount offers</h2>
        <p className="text-sm text-slate-400">
          Pre-applied Stripe promotion codes for upgrade checkout. Deadlines and redemption
          limits are enforced server-side.
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          <input
            type="text"
            value={offerCode}
            onChange={(e) => setOfferCode(e.target.value.toUpperCase())}
            placeholder="Offer code (optional — auto-generated)"
            className={inputCls}
          />
          <input
            type="text"
            value={offerStripePromoId}
            onChange={(e) => setOfferStripePromoId(e.target.value)}
            placeholder="Stripe promotion code ID (promo_…)"
            className={inputCls}
          />
          <input
            type="text"
            value={offerDisplayName}
            onChange={(e) => setOfferDisplayName(e.target.value)}
            placeholder="Display name"
            className={inputCls}
          />
          <input
            type="text"
            value={offerPlans}
            onChange={(e) => setOfferPlans(e.target.value)}
            placeholder="Plan codes (comma-separated)"
            className={inputCls}
          />
          <input
            type="number"
            min={1}
            value={offerMax}
            onChange={(e) => setOfferMax(e.target.value)}
            placeholder="Max redemptions (optional)"
            className={inputCls}
          />
          <input
            type="datetime-local"
            value={offerExpiresAt}
            onChange={(e) => setOfferExpiresAt(e.target.value)}
            className={inputCls}
          />
        </div>
        <button
          disabled={isPending || !offerStripePromoId.trim()}
          onClick={() =>
            runAction(async () => {
              const code = offerCode.trim() || generatePromoCode()
              const applicable_plan_codes = offerPlans
                .split(",")
                .map((part) => part.trim())
                .filter(Boolean)
              const res = await createAdminPromoCode(token, {
                code,
                grant_type: "price_discount",
                payload: {
                  stripe_promotion_code_id: offerStripePromoId.trim(),
                  applicable_plan_codes,
                  display_name: offerDisplayName.trim() || undefined,
                },
                max_redemptions: offerMax ? parseInt(offerMax, 10) : null,
                expires_at: offerExpiresAt
                  ? new Date(offerExpiresAt).toISOString()
                  : null,
              })
              showAuditToast(res.audit_log_id)
              setDiscountOffers((prev) => [res.promo_code, ...prev])
              setOfferCode("")
              setOfferStripePromoId("")
              setOfferDisplayName("")
              setOfferMax("")
              setOfferExpiresAt("")
            })
          }
          className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create checkout offer
        </button>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <th className="py-2 pr-4">Code</th>
                <th className="py-2 pr-4">Offer</th>
                <th className="py-2 pr-4">Expires</th>
                <th className="py-2 pr-4">Redemptions</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2">&nbsp;</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {discountOffers.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-500">
                    No checkout offers yet.
                  </td>
                </tr>
              )}
              {discountOffers.map((promo) => (
                <tr key={promo.id}>
                  <td className="py-3 pr-4 font-mono text-white">{promo.code}</td>
                  <td className="py-3 pr-4 text-slate-300">{promo.offer_summary}</td>
                  <td className="py-3 pr-4 text-slate-300">
                    {promo.expires_at
                      ? new Date(promo.expires_at).toLocaleString()
                      : "—"}
                  </td>
                  <td className="py-3 pr-4 text-slate-300">
                    {promo.redemption_count}
                    {promo.max_redemptions != null ? ` / ${promo.max_redemptions}` : ""}
                  </td>
                  <td className="py-3 pr-4">
                    <span
                      className={clsx(
                        "text-xs px-2 py-0.5 rounded-full border",
                        promo.is_redeemable
                          ? "border-emerald-700/40 text-emerald-300 bg-emerald-900/20"
                          : "border-slate-700 text-slate-400 bg-slate-800/50",
                      )}
                    >
                      {promo.is_redeemable ? "Active" : "Unavailable"}
                    </span>
                  </td>
                  <td className="py-3 text-right space-x-2">
                    <button
                      type="button"
                      onClick={() => void navigator.clipboard.writeText(promo.code)}
                      className="text-slate-400 hover:text-white"
                      title="Copy code"
                    >
                      <Copy className="w-4 h-4 inline" />
                    </button>
                    {promo.is_active && (
                      <button
                        disabled={isPending}
                        onClick={() =>
                          runAction(async () => {
                            const res = await patchAdminPromoCode(token, promo.id, {
                              is_active: false,
                            })
                            showAuditToast(res.audit_log_id)
                            setDiscountOffers((prev) =>
                              prev.map((p) =>
                                p.id === promo.id ? res.promo_code : p,
                              ),
                            )
                          })
                        }
                        className="text-xs text-red-300 hover:text-red-200"
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="text-xs text-slate-500 flex items-center gap-2">
        <Tag className="w-3.5 h-3.5" />
        Per-user coupons are issued from the Users drawer.
      </p>
    </div>
  )
}
