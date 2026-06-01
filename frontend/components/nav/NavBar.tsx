"use client"

import { useState, useRef, useEffect } from "react"
import Link from "next/link"
import { signOut, useSession } from "next-auth/react"
import { ChevronDown, CreditCard, FileText, LogOut, Settings, Sparkles } from "lucide-react"
import { logoutUser } from "@/lib/auth/api"
import { clsx } from "clsx"
import { JobsNavItem } from "@/components/nav/JobsNavItem"
import { NotificationBell } from "@/components/nav/NotificationBell"
import { UsageWidget } from "@/components/nav/UsageWidget"

export function NavBar() {
  const { data: session, status } = useSession()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

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

  return (
    <nav className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2 text-white font-semibold hover:opacity-80 transition-opacity shrink-0">
          <Sparkles className="w-5 h-5 text-amber-400" />
          <span className="hidden sm:inline">Smart Resume</span>
        </Link>

        {/* Nav links (authenticated) */}
        {status === "authenticated" && session && (
          <div className="flex items-center gap-1 text-sm text-slate-400 overflow-x-auto">
            <NavLink href="/session/new">New session</NavLink>
            <NavLink href="/profile">Edit master resume</NavLink>
            <NavLink href="/fit">Job fit</NavLink>
            <NavLink href="/dashboard">Dashboard</NavLink>
            <NavLink href="/tracker">Tracker</NavLink>
            <JobsNavItem />
          </div>
        )}

        {/* Right side */}
        <div className="flex items-center gap-2 shrink-0">
          {status === "authenticated" && session && (
            <>
              <NotificationBell />
              <UsageWidget />
            </>
          )}
          {status === "loading" ? (
            <div className="w-20 h-7 bg-slate-800 rounded animate-pulse" />
          ) : status === "authenticated" && session ? (
            <UserMenu
              displayName={session.backendUser?.display_name ?? session.user?.name ?? "You"}
              email={session.user?.email ?? ""}
              creditBalance={session.backendUser?.credit_balance}
              dropdownOpen={dropdownOpen}
              setDropdownOpen={setDropdownOpen}
              dropdownRef={dropdownRef}
              onLogout={handleLogout}
            />
          ) : (
            <Link
              href="/auth"
              className="bg-amber-400 text-slate-900 font-semibold text-sm px-4 py-1.5 rounded-lg hover:bg-amber-300 transition-colors"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </nav>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-slate-200 transition-colors whitespace-nowrap"
    >
      {children}
    </Link>
  )
}

interface UserMenuProps {
  displayName: string
  email: string
  creditBalance?: number
  dropdownOpen: boolean
  setDropdownOpen: React.Dispatch<React.SetStateAction<boolean>>
  dropdownRef: React.RefObject<HTMLDivElement | null>
  onLogout: () => void
}

function UserMenu({
  displayName,
  email,
  creditBalance,
  dropdownOpen,
  setDropdownOpen,
  dropdownRef,
  onLogout,
}: UserMenuProps) {
  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setDropdownOpen((v) => !v)}
        className="flex items-center gap-2 hover:bg-slate-800 rounded-lg px-2 py-1.5 transition-colors"
        aria-haspopup="true"
        aria-expanded={dropdownOpen}
      >
        {/* Avatar */}
        <div className="w-7 h-7 rounded-full bg-amber-400/20 border border-amber-400/30 flex items-center justify-center text-amber-400 text-xs font-semibold">
          {initials}
        </div>
        <span className="text-sm text-slate-200 max-w-[120px] truncate hidden sm:block">
          {displayName}
        </span>
        <ChevronDown
          className={clsx(
            "w-4 h-4 text-slate-500 transition-transform hidden sm:block",
            dropdownOpen && "rotate-180",
          )}
        />
      </button>

      {/* Dropdown */}
      {dropdownOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-slate-900 border border-slate-800 rounded-xl shadow-xl overflow-hidden z-50">
          {/* User info */}
          <div className="px-4 py-3 border-b border-slate-800">
            <p className="text-sm font-medium text-slate-200 truncate">{displayName}</p>
            <p className="text-xs text-slate-500 truncate">{email}</p>
            {creditBalance !== undefined && (
              <p className="text-xs text-amber-400 mt-0.5">
                {creditBalance} credit{creditBalance !== 1 ? "s" : ""} remaining
              </p>
            )}
          </div>

          {/* Menu items */}
          <div className="p-1">
            <DropdownItem href="/profile" icon={<Settings className="w-4 h-4" />}>
              Profile &amp; settings
            </DropdownItem>
            <DropdownItem href="/billing" icon={<CreditCard className="w-4 h-4" />}>
              Billing
            </DropdownItem>
            <DropdownItem href="/settings/notifications" icon={<Settings className="w-4 h-4" />}>
              Notifications
            </DropdownItem>
            <DropdownItem href="/dashboard" icon={<FileText className="w-4 h-4" />}>
              My resumes
            </DropdownItem>
          </div>

          <div className="p-1 border-t border-slate-800">
            <button
              onClick={onLogout}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-950/40 rounded-lg transition-colors"
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
      className="flex items-center gap-2.5 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
    >
      <span className="text-slate-500">{icon}</span>
      {children}
    </Link>
  )
}
