"use client"

import { useState, useRef, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut, useSession } from "next-auth/react"
import {
  ChevronDown,
  CreditCard,
  FileText,
  LayoutDashboard,
  LogOut,
  Search,
  Settings,
  Sparkles,
  Target,
} from "lucide-react"
import { BrandLogo } from "@/components/brand/BrandLogo"
import { fetchMe, logoutUser } from "@/lib/auth/api"
import { clsx } from "clsx"
import { NotificationBell } from "@/components/nav/NotificationBell"
import { UsageWidget } from "@/components/nav/UsageWidget"
import { ThemeToggle } from "@/components/theme/ThemeToggle"

const PRIMARY_LINKS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/profile", label: "Master resume", icon: FileText },
  { href: "/jobs/setup", label: "Job roles", icon: Target },
  { href: "/jobs", label: "Jobs", icon: Search },
  { href: "/session/new", label: "Tailor", icon: Sparkles },
] as const

const MORE_LINKS = [
  { href: "/tracker", label: "Tracker" },
  { href: "/fit", label: "Job fit" },
  { href: "/career-watch", label: "Career Watch" },
  { href: "/cover-letter/new", label: "Cover letter" },
] as const

export function NavBar() {
  const pathname = usePathname()
  const { data: session, status } = useSession()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const moreRef = useRef<HTMLDivElement>(null)
  const [hadUserMenu, setHadUserMenu] = useState(false)

  const accessToken =
    session?.error === "TokenExpired" ? undefined : session?.backendAccessToken

  const showUserMenu = Boolean(session?.user ?? session?.backendAccessToken)
  useEffect(() => {
    if (showUserMenu) {
      setHadUserMenu(true)
    } else if (status === "unauthenticated") {
      setHadUserMenu(false)
    }
  }, [showUserMenu, status])

  const renderUserMenu =
    showUserMenu || (status === "loading" && hadUserMenu)

  useEffect(() => {
    if (!dropdownOpen) return
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [dropdownOpen])

  useEffect(() => {
    if (!moreOpen) return
    function handleClick(e: MouseEvent) {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [moreOpen])

  async function handleLogout() {
    setDropdownOpen(false)
    try {
      if (session?.backendAccessToken) {
        await logoutUser(session.backendAccessToken)
      }
    } catch {
      // Continue with NextAuth sign-out even if backend call fails
    }
    await signOut({ callbackUrl: "/" })
  }

  function isActive(href: string) {
    if (href === "/dashboard") return pathname === "/dashboard"
    if (href === "/jobs/setup") return pathname.startsWith("/jobs/setup")
    return pathname === href || pathname.startsWith(`${href}/`)
  }

  return (
    <nav className="border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 backdrop-blur-sm sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between gap-3">
        <Link href="/dashboard" className="flex items-center hover:opacity-90 transition-opacity shrink-0 py-1">
          <BrandLogo className="h-10 w-auto max-w-[200px] sm:max-w-[240px]" />
        </Link>

        {renderUserMenu && (
          <div className="hidden md:flex items-center gap-0.5 text-sm text-slate-600 dark:text-slate-400 min-w-0">
            {PRIMARY_LINKS.map(({ href, label }) => (
              <NavLink key={href} href={href} active={isActive(href)}>
                {label}
              </NavLink>
            ))}
            <div className="relative" ref={moreRef}>
              <button
                type="button"
                onClick={() => setMoreOpen((v) => !v)}
                className={clsx(
                  "inline-flex items-center gap-1 px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap",
                  moreOpen
                    ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-200"
                    : "hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200",
                )}
              >
                More
                <ChevronDown className={clsx("w-4 h-4 transition-transform", moreOpen && "rotate-180")} />
              </button>
              {moreOpen && (
                <div className="absolute left-0 mt-2 w-44 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-xl overflow-hidden z-50">
                  {MORE_LINKS.map(({ href, label }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMoreOpen(false)}
                      className="block px-4 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      {label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {renderUserMenu && (
          <div className="md:hidden shrink-0">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400/15 text-amber-900 dark:text-amber-200 text-sm font-medium"
            >
              <LayoutDashboard className="w-4 h-4" />
              Dashboard
            </Link>
          </div>
        )}

        <div className="flex items-center gap-2 shrink-0 ml-auto md:ml-0">
          <ThemeToggle />
          {renderUserMenu && (
            <>
              <NotificationBell />
              <UsageWidget />
            </>
          )}
          {renderUserMenu ? (
            <UserMenu
              displayName={session!.backendUser?.display_name ?? session!.user?.name ?? "You"}
              email={session!.user?.email ?? ""}
              creditBalance={session!.backendUser?.credit_balance}
              accessToken={accessToken}
              dropdownOpen={dropdownOpen}
              setDropdownOpen={setDropdownOpen}
              dropdownRef={dropdownRef}
              onLogout={handleLogout}
            />
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/auth"
                className="text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 text-sm font-medium px-3 py-1.5 transition-colors"
              >
                Sign in
              </Link>
              <Link
                href="/auth?mode=register"
                className="bg-amber-400 text-slate-900 font-semibold text-sm px-4 py-1.5 rounded-lg hover:bg-amber-300 transition-colors"
              >
                Register
              </Link>
            </div>
          )}
        </div>
      </div>

      {renderUserMenu && (
        <div className="md:hidden border-t border-slate-200 dark:border-slate-800 px-2 py-2 flex gap-1 overflow-x-auto text-xs">
          {PRIMARY_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "px-3 py-1.5 rounded-lg whitespace-nowrap shrink-0",
                isActive(href)
                  ? "bg-amber-400/20 text-amber-900 dark:text-amber-200 font-medium"
                  : "text-slate-600 dark:text-slate-400",
              )}
            >
              {label}
            </Link>
          ))}
          <span className="mx-1 self-center h-4 w-px bg-slate-200 dark:bg-slate-700 shrink-0" aria-hidden />
          {MORE_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "px-3 py-1.5 rounded-lg whitespace-nowrap shrink-0",
                isActive(href)
                  ? "bg-amber-400/20 text-amber-900 dark:text-amber-200 font-medium"
                  : "text-slate-600 dark:text-slate-400",
              )}
            >
              {label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  )
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string
  active?: boolean
  children: React.ReactNode
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap",
        active
          ? "bg-amber-400/15 text-amber-900 dark:text-amber-200 font-medium"
          : "hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200",
      )}
    >
      {children}
    </Link>
  )
}

interface UserMenuProps {
  displayName: string
  email: string
  creditBalance?: number
  accessToken?: string
  dropdownOpen: boolean
  setDropdownOpen: React.Dispatch<React.SetStateAction<boolean>>
  dropdownRef: React.RefObject<HTMLDivElement | null>
  onLogout: () => void
}

function UserMenu({
  displayName,
  email,
  creditBalance,
  accessToken,
  dropdownOpen,
  setDropdownOpen,
  dropdownRef,
  onLogout,
}: UserMenuProps) {
  const [liveCredits, setLiveCredits] = useState<number | undefined>(creditBalance)
  const fetchedForOpenRef = useRef(false)

  useEffect(() => {
    setLiveCredits(creditBalance)
  }, [creditBalance])

  useEffect(() => {
    if (!dropdownOpen) {
      fetchedForOpenRef.current = false
      return
    }
    if (!accessToken || fetchedForOpenRef.current) return
    fetchedForOpenRef.current = true

    let cancelled = false
    void fetchMe(accessToken)
      .then((user) => {
        if (!cancelled) setLiveCredits(user.credit_balance)
      })
      .catch(() => {
        if (!cancelled) setLiveCredits(creditBalance)
      })

    return () => {
      cancelled = true
    }
  }, [dropdownOpen, accessToken, creditBalance])

  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setDropdownOpen((v) => !v)}
        className="flex items-center gap-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg px-2 py-1.5 transition-colors"
        aria-haspopup="true"
        aria-expanded={dropdownOpen}
      >
        <div className="w-7 h-7 rounded-full bg-amber-500/20 dark:bg-amber-400/20 border border-amber-500/40 dark:border-amber-400/30 flex items-center justify-center text-amber-700 dark:text-amber-400 text-xs font-semibold">
          {initials}
        </div>
        <span className="text-sm text-slate-800 dark:text-slate-200 max-w-[120px] truncate hidden sm:block">
          {displayName}
        </span>
        <ChevronDown
          className={clsx(
            "w-4 h-4 text-slate-600 dark:text-slate-400 transition-transform hidden sm:block",
            dropdownOpen && "rotate-180",
          )}
        />
      </button>

      {dropdownOpen && (
        <div
          className="absolute right-0 mt-2 w-56 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-xl overflow-hidden z-50"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{displayName}</p>
            <p className="text-xs text-slate-600 dark:text-slate-400 truncate">{email}</p>
            {liveCredits !== undefined && (
              <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
                {liveCredits} credit{liveCredits !== 1 ? "s" : ""} remaining
              </p>
            )}
          </div>

          <div className="p-1">
            <DropdownItem href="/dashboard" icon={<LayoutDashboard className="w-4 h-4" />}>
              Dashboard
            </DropdownItem>
            <DropdownItem href="/profile" icon={<Settings className="w-4 h-4" />}>
              Profile &amp; settings
            </DropdownItem>
            <DropdownItem href="/billing" icon={<CreditCard className="w-4 h-4" />}>
              Billing
            </DropdownItem>
          </div>

          <div className="p-1 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => void onLogout()}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 rounded-lg transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function DropdownItem({
  href,
  icon,
  children,
}: {
  href: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 px-3 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
    >
      <span className="text-slate-600 dark:text-slate-400">{icon}</span>
      {children}
    </Link>
  )
}
