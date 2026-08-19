"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  AlertTriangle,
  BarChart2,
  Bell,
  ChevronRight,
  ClipboardList,
  CreditCard,
  FileText,
  Flag,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  Settings,
  Shield,
  Sparkles,
  Tag,
  Users,
  Zap,
} from "lucide-react"
import { clsx } from "clsx"
import {
  getAdminSession,
  clearAdminSession,
  sessionExpiringSoon,
  sessionMsRemaining,
} from "@/lib/admin/session"
import { adminLogout } from "@/lib/admin/api"
import type { StoredAdminSession } from "@/lib/admin/session"

// ── Types ─────────────────────────────────────────────────────────────────────

interface ToastMessage {
  id: string
  message: string
}

// ── Audit toast context ───────────────────────────────────────────────────────

import { createContext, useContext } from "react"

interface AuditToastContextValue {
  showAuditToast: (auditLogId: string) => void
}
export const AuditToastContext = createContext<AuditToastContextValue>({
  showAuditToast: () => {},
})
export function useAuditToast() {
  return useContext(AuditToastContext)
}

// ── Admin session context ─────────────────────────────────────────────────────

interface AdminSessionContextValue {
  session: StoredAdminSession | null
  token: string | null
}
export const AdminSessionContext = createContext<AdminSessionContextValue>({
  session: null,
  token: null,
})
export function useAdminSession() {
  return useContext(AdminSessionContext)
}

// ── Nav links ─────────────────────────────────────────────────────────────────

const NAV_LINKS = [
  { href: "/admin/plans", label: "Plans & Pricing", icon: CreditCard },
  { href: "/admin/promo", label: "Promo & credits", icon: Tag },
  { href: "/admin/llm", label: "LLM Config", icon: Zap },
  { href: "/admin/flags", label: "Feature Flags", icon: Flag },
  { href: "/admin/announcements", label: "Announcements", icon: Bell },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/refunds", label: "Refunds", icon: RefreshCw },
  { href: "/admin/reports", label: "Reports", icon: BarChart2 },
  { href: "/admin/system", label: "System Health", icon: Settings },
  { href: "/admin/audit", label: "Audit Log", icon: ClipboardList },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMs(ms: number): string {
  const totalSec = Math.ceil(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

// ── Admin Shell Layout ────────────────────────────────────────────────────────

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()

  const [session, setSession] = useState<StoredAdminSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [timeLeft, setTimeLeft] = useState<number | null>(null)
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const toastTimersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  // Load session once on mount; redirect to /admin/auth if none exists.
  useEffect(() => {
    const isAuthPage = pathname === "/admin/auth"
    getAdminSession().then((s) => {
      if (!s && !isAuthPage) {
        router.replace("/admin/auth")
        return
      }
      setSession(s)
      setLoading(false)
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for backend session-revoked signals from req() and redirect immediately.
  useEffect(() => {
    const isAuthPage = pathname === "/admin/auth"
    if (isAuthPage) return
    async function handleUnauthorized() {
      await clearAdminSession()
      router.replace("/admin/auth?reason=session_revoked")
    }
    window.addEventListener("admin:unauthorized", handleUnauthorized)
    return () => window.removeEventListener("admin:unauthorized", handleUnauthorized)
  }, [pathname, router])

  // Countdown timer for session TTL warning
  useEffect(() => {
    if (!session) return
    timerRef.current = setInterval(() => {
      const ms = sessionMsRemaining(session)
      setTimeLeft(ms)
      if (ms === 0) {
        clearInterval(timerRef.current!)
        router.replace("/admin/auth?reason=expired")
      }
    }, 1000)
    return () => clearInterval(timerRef.current!)
  }, [session, router])

  const showAuditToast = useCallback((auditLogId: string) => {
    const id = crypto.randomUUID()
    setToasts((prev) => [...prev, { id, message: `✓ Audited (id: ${auditLogId})` }])
    const timeout = setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      5000,
    )
    toastTimersRef.current.push(timeout)
  }, [])

  useEffect(
    () => () => {
      toastTimersRef.current.forEach(clearTimeout)
    },
    [],
  )

  async function handleLogout() {
    if (session?.access_token) {
      try {
        await adminLogout(session.access_token)
      } catch {
        // Ignore backend errors on logout
      }
    }
    await clearAdminSession()
    router.replace("/admin/auth")
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-amber-400" />
      </div>
    )
  }

  const expiringSoon = session ? sessionExpiringSoon(session) : false
  const roleBadgeColor =
    session?.admin.role === "super-admin"
      ? "bg-red-900/60 text-red-300"
      : session?.admin.role === "support-agent"
        ? "bg-amber-900/60 text-amber-300"
        : "bg-slate-700 text-slate-300"

  return (
    <AdminSessionContext.Provider
      value={{ session, token: session?.access_token ?? null }}
    >
      <AuditToastContext.Provider value={{ showAuditToast }}>
        <div className="min-h-screen bg-slate-950 text-slate-100 flex">
          {/* ── Sidebar ───────────────────────────────────────────────────── */}
          <aside
            className={clsx(
              "fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 border-r border-slate-800 flex flex-col transition-transform duration-200",
              sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
            )}
          >
            {/* Brand */}
            <div className="h-14 flex items-center gap-2 px-4 border-b border-slate-800 shrink-0">
              <Shield className="w-5 h-5 text-red-400" />
              <span className="font-semibold text-white">Admin Panel</span>
              <Link
                href="/"
                className="ml-auto text-slate-500 hover:text-slate-300 transition-colors"
                title="Back to app"
              >
                <Sparkles className="w-4 h-4" />
              </Link>
            </div>

            {/* Admin info */}
            {session && (
              <div className="px-4 py-3 border-b border-slate-800 shrink-0">
                <p className="text-sm font-medium text-white truncate">
                  {session.admin.display_name}
                </p>
                <p className="text-xs text-slate-400 truncate">{session.admin.email}</p>
                <span
                  className={clsx(
                    "mt-1.5 inline-block px-2 py-0.5 rounded text-xs font-medium",
                    roleBadgeColor,
                  )}
                >
                  {session.admin.role}
                </span>
              </div>
            )}

            {/* Nav */}
            <nav className="flex-1 overflow-y-auto py-3 space-y-0.5 px-2">
              {NAV_LINKS.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || pathname.startsWith(href + "/")
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setSidebarOpen(false)}
                    className={clsx(
                      "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                      active
                        ? "bg-slate-700 text-white"
                        : "text-slate-400 hover:bg-slate-800 hover:text-slate-200",
                    )}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    {label}
                    {active && (
                      <ChevronRight className="w-3 h-3 ml-auto text-slate-500" />
                    )}
                  </Link>
                )
              })}
            </nav>

            {/* Logout */}
            <div className="px-2 py-3 border-t border-slate-800 shrink-0">
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-slate-400 hover:bg-red-900/30 hover:text-red-300 transition-colors"
              >
                <LogOut className="w-4 h-4 shrink-0" />
                Logout
              </button>
            </div>
          </aside>

          {/* ── Main area ─────────────────────────────────────────────────── */}
          <div className="flex-1 flex flex-col min-w-0 lg:pl-64">
            {/* Top bar (mobile + session warning) */}
            <header className="h-14 border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-40 flex items-center gap-3 px-4">
              {/* Mobile menu toggle */}
              <button
                className="lg:hidden text-slate-400 hover:text-white transition-colors"
                onClick={() => setSidebarOpen((o) => !o)}
                aria-label="Toggle sidebar"
              >
                <LayoutDashboard className="w-5 h-5" />
              </button>

              {/* Breadcrumb */}
              <span className="text-sm text-slate-400 hidden sm:block">
                {NAV_LINKS.find((l) => pathname.startsWith(l.href))?.label ?? "Admin"}
              </span>

              {/* Session warning banner */}
              {expiringSoon && timeLeft !== null && (
                <div className="ml-auto flex items-center gap-2 bg-amber-900/40 border border-amber-700/50 text-amber-300 text-xs px-3 py-1.5 rounded-lg">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  Session expires in {fmtMs(timeLeft)}
                </div>
              )}
            </header>

            {/* Session warning — full banner when very close */}
            {expiringSoon && timeLeft !== null && timeLeft < 2 * 60 * 1000 && (
              <div className="bg-amber-900/30 border-b border-amber-700/50 px-4 py-2 flex items-center gap-2 text-amber-200 text-sm">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>
                  Your admin session expires in {fmtMs(timeLeft)}. Save your work and
                  re-authenticate.
                </span>
              </div>
            )}

            {/* Page content */}
            <main className="flex-1 p-6 min-w-0">{children}</main>
          </div>

          {/* Sidebar backdrop (mobile) */}
          {sidebarOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/50 lg:hidden"
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* ── Audit toasts ───────────────────────────────────────────────── */}
          <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
            {toasts.map((t) => (
              <div
                key={t.id}
                className="bg-emerald-900/90 border border-emerald-600/50 text-emerald-200 text-sm px-4 py-2.5 rounded-lg shadow-lg animate-in fade-in slide-in-from-bottom-2 pointer-events-auto"
              >
                {t.message}
              </div>
            ))}
          </div>
        </div>
      </AuditToastContext.Provider>
    </AdminSessionContext.Provider>
  )
}
