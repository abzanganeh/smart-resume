"use client"

import { useEffect, useState, useTransition } from "react"
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Loader2,
  X,
  AlertOctagon,
  Download,
  Trash2,
  CreditCard,
  Copy,
  ShieldOff,
  ShieldCheck,
  Info,
} from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  getAdminUsers,
  getAdminUserDetail,
  adjustUserCredits,
  createAdminPromoCode,
  listAdminUserPromoCodes,
  suspendUser,
  unsuspendUser,
  triggerUserExport,
  closeUserAccount,
  deleteUserImmediately,
} from "@/lib/admin/api"
import type {
  AdminUser,
  AdminUserDetail,
  CreditTransaction,
  LoginHistoryEntry,
  PromoCode,
} from "@/lib/admin/types"
import { generatePromoCode } from "@/lib/admin/promoCode"

const PER_PAGE = 25

// ── Users Page ────────────────────────────────────────────────────────────────

export default function AdminUsersPage() {
  const { token, session } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [detailUser, setDetailUser] = useState<AdminUserDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 350)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => {
    setPage(1)
  }, [debouncedQuery])

  useEffect(() => {
    if (!token) return
    loadUsers()
  }, [token, page, debouncedQuery]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadUsers() {
    setLoading(true)
    setError(null)
    try {
      const res = await getAdminUsers(token!, { q: debouncedQuery || undefined, page, per_page: PER_PAGE })
      setUsers(Array.isArray(res.users) ? res.users : [])
      setTotal(res.total ?? 0)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users")
    } finally {
      setLoading(false)
    }
  }

  async function openUserDetail(userId: string) {
    setSelectedUserId(userId)
    setDetailUser(null)
    setDetailLoading(true)
    try {
      const u = await getAdminUserDetail(token!, userId)
      setDetailUser(u)
    } finally {
      setDetailLoading(false)
    }
  }

  function refreshDetailUser(updated: Partial<AdminUserDetail>) {
    setDetailUser((prev) => (prev ? { ...prev, ...updated } : prev))
    setUsers((prev) =>
      prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)),
    )
  }

  const totalPages = Math.ceil(total / PER_PAGE)
  const isSuperAdmin = session?.admin.role === "super-admin"

  if (!token) return <NotAuthed />

  return (
    <div className="space-y-5 max-w-6xl">
      <h1 className="text-xl font-semibold text-white">User Management</h1>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by email, ID, or Stripe customer ID…"
          className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
        />
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <Th>Email</Th>
                <Th>Tier</Th>
                <Th>Credits</Th>
                <Th>Plan</Th>
                <Th>Status</Th>
                <Th>Joined</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading && (
                <tr>
                  <td colSpan={6} className="py-10 text-center">
                    <Loader2 className="w-6 h-6 animate-spin text-amber-400 mx-auto" />
                  </td>
                </tr>
              )}
              {!loading && users.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-slate-500">
                    No users found.
                  </td>
                </tr>
              )}
              {!loading &&
                users.map((u) => (
                  <tr
                    key={u.id}
                    onClick={() => openUserDetail(u.id)}
                    className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                  >
                    <Td>
                      <div className="flex items-center gap-2">
                        <span className="text-white">{u.email}</span>
                        {u.suspended_at && (
                          <AlertOctagon className="w-3.5 h-3.5 text-red-400 shrink-0" aria-label="Suspended" />
                        )}
                      </div>
                      <span className="text-xs text-slate-500 font-mono">{u.id.slice(0, 8)}…</span>
                    </Td>
                    <Td>
                      <TierBadge tier={u.tier} />
                    </Td>
                    <Td className="font-mono">{u.credit_balance}</Td>
                    <Td className="text-slate-400">
                      {u.subscription_status ?? <span className="text-slate-600">—</span>}
                    </Td>
                    <Td>
                      {u.suspended_at ? (
                        <span className="text-xs text-red-400 bg-red-900/30 px-2 py-0.5 rounded-full">
                          Suspended
                        </span>
                      ) : u.closure_requested_at ? (
                        <span className="text-xs text-amber-400">Closing</span>
                      ) : (
                        <span className="text-xs text-emerald-400">Active</span>
                      )}
                    </Td>
                    <Td className="text-xs text-slate-500">
                      {new Date(u.created_at).toLocaleDateString()}
                    </Td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-800">
            <span className="text-xs text-slate-500">
              {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, total)} of {total}
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="p-1.5 rounded text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-slate-400">
                {page} / {totalPages}
              </span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="p-1.5 rounded text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail drawer */}
      {selectedUserId && (
        <UserDetailDrawer
          loading={detailLoading}
          user={detailUser}
          isSuperAdmin={isSuperAdmin}
          token={token}
          onClose={() => setSelectedUserId(null)}
          onRefresh={refreshDetailUser}
          showAuditToast={showAuditToast}
        />
      )}
    </div>
  )
}

// ── User Detail Drawer ────────────────────────────────────────────────────────

function UserDetailDrawer({
  loading,
  user,
  isSuperAdmin,
  token,
  onClose,
  onRefresh,
  showAuditToast,
}: {
  loading: boolean
  user: AdminUserDetail | null
  isSuperAdmin: boolean
  token: string
  onClose: () => void
  onRefresh: (data: Partial<AdminUserDetail>) => void
  showAuditToast: (id: string) => void
}) {
  const [creditAmount, setCreditAmount] = useState("")
  const [creditReason, setCreditReason] = useState("")
  const [couponAmount, setCouponAmount] = useState("5")
  const [couponCode, setCouponCode] = useState("")
  const [issuedCode, setIssuedCode] = useState<string | null>(null)
  const [userPromos, setUserPromos] = useState<PromoCode[]>([])
  const [suspendReason, setSuspendReason] = useState("")
  const [confirmDelete, setConfirmDelete] = useState("")
  const [activeTab, setActiveTab] = useState<"overview" | "credits" | "history">("overview")
  const [actionError, setActionError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const DRAWER_TABS = ["overview", "credits", "history"] as const

  useEffect(() => {
    if (!user || !token) return
    void listAdminUserPromoCodes(token, user.id)
      .then(setUserPromos)
      .catch(() => setUserPromos([]))
  }, [user?.id, token])

  function runAction(fn: () => Promise<void>) {
    setActionError(null)
    startTransition(async () => {
      try {
        await fn()
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Action failed")
      }
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      {/* Drawer */}
      <div className="relative w-full max-w-xl bg-slate-900 border-l border-slate-800 overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 sticky top-0 bg-slate-900 z-10">
          <h2 className="font-medium text-white">User Detail</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center flex-1 py-20">
            <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
          </div>
        )}

        {!loading && user && (
          <div className="flex-1">
            {/* User summary */}
            <div className="px-5 py-4 border-b border-slate-800 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-white font-medium">{user.email}</p>
                {user.suspended_at && (
                  <span className="text-xs bg-red-900/40 text-red-300 border border-red-700/40 px-2 py-0.5 rounded-full">
                    Suspended
                  </span>
                )}
                {user.closure_requested_at && (
                  <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded-full">
                    Closing
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 font-mono">{user.id}</p>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <InfoRow label="Tier" value={<TierBadge tier={user.tier} />} />
                <InfoRow label="Credits" value={<span className="font-mono text-white">{user.credit_balance}</span>} />
                <InfoRow label="Plan" value={user.subscription_status ?? "—"} />
                <InfoRow label="Resumes" value={String(user.resume_count)} />
                {user.stripe_customer_id && (
                  <InfoRow label="Stripe ID" value={<code className="text-xs text-slate-400">{user.stripe_customer_id}</code>} />
                )}
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-slate-800 px-5">
              {DRAWER_TABS.map((t) => (
                <button
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={clsx(
                    "py-3 mr-4 text-sm border-b-2 transition-colors capitalize",
                    activeTab === t
                      ? "border-amber-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>

            {actionError && (
              <div className="mx-5 mt-4 bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
                {actionError}
              </div>
            )}

            {/* Overview tab */}
            {activeTab === "overview" && (
              <div className="p-5 space-y-4">
                {/* Adjust credits */}
                <DrawerSection title="Adjust Credits" icon={CreditCard}>
                  <div className="space-y-3">
                    <div className="flex gap-3">
                      <input
                        type="number"
                        value={creditAmount}
                        onChange={(e) => setCreditAmount(e.target.value)}
                        placeholder="±N credits"
                        className={inputCls + " w-28"}
                      />
                      <input
                        type="text"
                        value={creditReason}
                        onChange={(e) => setCreditReason(e.target.value)}
                        placeholder="Reason (required)"
                        className={inputCls + " flex-1"}
                      />
                    </div>
                    <button
                      disabled={!creditAmount || !creditReason || isPending}
                      onClick={() =>
                        runAction(async () => {
                          const res = await adjustUserCredits(token, user.id, {
                            amount: parseInt(creditAmount),
                            reason: creditReason,
                          })
                          showAuditToast(res.audit_log_id)
                          onRefresh({ id: user.id, credit_balance: res.data.new_balance })
                          setCreditAmount("")
                          setCreditReason("")
                        })
                      }
                      className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                    >
                      {isPending && <Loader2 className="w-3 h-3 animate-spin" />}
                      Apply adjustment
                    </button>
                  </div>
                </DrawerSection>

                <DrawerSection title="Issue coupon" icon={Copy}>
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">
                      Creates a code only this user can redeem on Billing.
                    </p>
                    <div className="flex gap-3">
                      <input
                        type="number"
                        min={1}
                        value={couponAmount}
                        onChange={(e) => setCouponAmount(e.target.value)}
                        placeholder="Credits"
                        className={inputCls + " w-28"}
                      />
                      <input
                        type="text"
                        value={couponCode}
                        onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
                        placeholder="Custom code (optional)"
                        className={inputCls + " flex-1"}
                      />
                    </div>
                    {issuedCode && (
                      <div className="flex items-center gap-2 text-xs text-emerald-300 bg-emerald-900/20 border border-emerald-800/40 rounded-lg px-3 py-2">
                        <span className="font-mono">{issuedCode}</span>
                        <button
                          type="button"
                          onClick={() => void navigator.clipboard.writeText(issuedCode)}
                          className="text-emerald-200 hover:text-white"
                        >
                          Copy
                        </button>
                      </div>
                    )}
                    <button
                      disabled={!couponAmount || isPending}
                      onClick={() =>
                        runAction(async () => {
                          const amount = parseInt(couponAmount, 10)
                          if (Number.isNaN(amount) || amount < 1) return
                          const code = couponCode.trim() || generatePromoCode()
                          const res = await createAdminPromoCode(token, {
                            code,
                            grant_type: "extra_credits",
                            payload: { amount, credit_kind: "free" },
                            restricted_user_id: user.id,
                          })
                          showAuditToast(res.audit_log_id)
                          setIssuedCode(res.promo_code.code)
                          setUserPromos((prev) => [res.promo_code, ...prev])
                          setCouponCode("")
                        })
                      }
                      className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                    >
                      {isPending && <Loader2 className="w-3 h-3 animate-spin" />}
                      Issue coupon
                    </button>
                    {userPromos.length > 0 && (
                      <ul className="space-y-2 text-xs text-slate-400">
                        {userPromos.map((promo) => (
                          <li key={promo.id} className="flex justify-between gap-2">
                            <span className="font-mono text-slate-300">{promo.code}</span>
                            <span>
                              {String((promo.payload as { amount?: number }).amount ?? "—")} cr ·{" "}
                              {promo.is_active ? "active" : "inactive"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </DrawerSection>

                {/* Suspend / Unsuspend */}
                {isSuperAdmin && (
                  <DrawerSection title={user.suspended_at ? "Unsuspend User" : "Suspend User"} icon={user.suspended_at ? ShieldCheck : ShieldOff}>
                    {!user.suspended_at ? (
                      <div className="space-y-3">
                        <input
                          type="text"
                          value={suspendReason}
                          onChange={(e) => setSuspendReason(e.target.value)}
                          placeholder="Reason for suspension"
                          className={inputCls}
                        />
                        <button
                          disabled={!suspendReason || isPending}
                          onClick={() =>
                            runAction(async () => {
                              const res = await suspendUser(token, user.id, suspendReason)
                              showAuditToast(res.audit_log_id)
                              onRefresh({ id: user.id, suspended_at: res.data.suspended_at })
                              setSuspendReason("")
                            })
                          }
                          className="flex items-center gap-2 bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                        >
                          {isPending && <Loader2 className="w-3 h-3 animate-spin" />}
                          Suspend user
                        </button>
                      </div>
                    ) : (
                      <button
                        disabled={isPending}
                        onClick={() =>
                          runAction(async () => {
                            const res = await unsuspendUser(token, user.id)
                            showAuditToast(res.audit_log_id)
                            onRefresh({ id: user.id, suspended_at: null })
                          })
                        }
                        className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                      >
                        {isPending && <Loader2 className="w-3 h-3 animate-spin" />}
                        Unsuspend user
                      </button>
                    )}
                  </DrawerSection>
                )}

                {/* Export / Close */}
                <DrawerSection title="Data Actions" icon={Download}>
                  <div className="flex flex-wrap gap-2">
                    <button
                      disabled={isPending}
                      onClick={() =>
                        runAction(async () => {
                          const res = await triggerUserExport(token, user.id)
                          showAuditToast(res.audit_log_id)
                        })
                      }
                      className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                    >
                      {isPending && <Loader2 className="w-3 h-3 animate-spin" />}
                      Trigger export
                    </button>
                    {isSuperAdmin && !user.closure_requested_at && (
                      <button
                        disabled={isPending}
                        onClick={() =>
                          runAction(async () => {
                            const res = await closeUserAccount(token, user.id)
                            showAuditToast(res.audit_log_id)
                            onRefresh({ id: user.id, closure_requested_at: res.data.closure_requested_at })
                          })
                        }
                        className="flex items-center gap-2 bg-amber-800 hover:bg-amber-700 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                      >
                        Initiate closure
                      </button>
                    )}
                  </div>
                </DrawerSection>

                {/* Delete immediately — super-admin only with type-to-confirm */}
                {isSuperAdmin && (
                  <DrawerSection title="Delete Immediately" icon={Trash2}>
                    <p className="text-xs text-red-400 mb-2">
                      Irreversible hard delete. Type <code className="font-mono">{user.email}</code> to confirm.
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={confirmDelete}
                        onChange={(e) => setConfirmDelete(e.target.value)}
                        placeholder="Type email to confirm"
                        className={inputCls + " flex-1 text-xs"}
                      />
                      <button
                        disabled={confirmDelete !== user.email || isPending}
                        onClick={() =>
                          runAction(async () => {
                            const res = await deleteUserImmediately(token, user.id)
                            showAuditToast(res.audit_log_id)
                            onClose()
                          })
                        }
                        className="flex items-center gap-2 bg-red-800 hover:bg-red-700 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap"
                      >
                        {isPending && <Loader2 className="w-3 h-3 animate-spin" />}
                        Delete
                      </button>
                    </div>
                  </DrawerSection>
                )}
              </div>
            )}

            {/* Credits tab */}
            {activeTab === "credits" && (
              <div className="p-5">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-400 border-b border-slate-800">
                      <Th>Amount</Th>
                      <Th>Reason</Th>
                      <Th>By</Th>
                      <Th>Date</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {user.credit_transactions.length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-6 text-center text-slate-500 text-xs">No transactions.</td>
                      </tr>
                    )}
                    {user.credit_transactions.map((tx: CreditTransaction) => (
                      <tr key={tx.id}>
                        <Td className={clsx("font-mono", tx.amount > 0 ? "text-emerald-400" : "text-red-400")}>
                          {tx.amount > 0 ? "+" : ""}{tx.amount}
                        </Td>
                        <Td className="text-xs">{tx.reason}</Td>
                        <Td className="text-xs text-slate-500 capitalize">{tx.initiated_by}</Td>
                        <Td className="text-xs text-slate-500">{new Date(tx.created_at).toLocaleDateString()}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Login history tab */}
            {activeTab === "history" && (
              <div className="p-5">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-400 border-b border-slate-800">
                      <Th>Event</Th>
                      <Th>IP</Th>
                      <Th>Date</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {user.login_history.length === 0 && (
                      <tr>
                        <td colSpan={3} className="py-6 text-center text-slate-500 text-xs">No login history.</td>
                      </tr>
                    )}
                    {user.login_history.map((e: LoginHistoryEntry) => (
                      <tr key={e.id}>
                        <Td>
                          <span className={clsx(
                            "text-xs px-1.5 py-0.5 rounded",
                            e.event === "login_success" ? "text-emerald-300" :
                            e.event === "login_failure" ? "text-red-300" :
                            "text-slate-300",
                          )}>
                            {e.event}
                          </span>
                        </Td>
                        <Td className="font-mono text-xs">{e.ip}</Td>
                        <Td className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString()}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Shared UI atoms ───────────────────────────────────────────────────────────

const inputCls =
  "bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"

function DrawerSection({
  title,
  icon: Icon,
  children,
}: {
  title: string
  icon: React.ElementType
  children: React.ReactNode
}) {
  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="w-3.5 h-3.5 text-slate-400" />
        <h3 className="text-xs font-medium text-slate-300">{title}</h3>
      </div>
      {children}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center gap-2">
      <span className="text-xs text-slate-400 shrink-0">{label}</span>
      <span className="text-sm text-slate-300 text-right">{value}</span>
    </div>
  )
}

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    free: "bg-slate-700 text-slate-300",
    standard: "bg-slate-700 text-slate-200",
    better: "bg-amber-900/60 text-amber-300",
    best: "bg-violet-900/60 text-violet-300",
  }
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full capitalize", colors[tier] ?? colors.free)}>
      {tier}
    </span>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="pb-2 pr-4 font-medium text-xs">{children}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={clsx("py-2.5 pr-4 text-slate-300 align-top", className)}>{children}</td>
}

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
}
