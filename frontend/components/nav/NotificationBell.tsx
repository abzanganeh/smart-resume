"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Bell } from "lucide-react";
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  type NotificationItem,
} from "@/lib/notifications";
import { cn } from "@/lib/utils";

const POLL_MS = 60_000;

export function NotificationBell() {
  const { data: session } = useSession();
  // Treat an expired backend token the same as no token — stop polling until re-auth.
  const token = session?.error === "TokenExpired" ? undefined : session?.backendAccessToken;
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const refreshCount = useCallback(async () => {
    if (!token) return;
    try {
      const { count } = await fetchUnreadCount(token);
      setUnread(count);
    } catch {
      /* ignore poll errors */
    }
  }, [token]);

  const loadInbox = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const { items: list } = await fetchNotifications(token, { limit: 10 });
      setItems(list);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refreshCount();
    const id = setInterval(refreshCount, POLL_MS);
    return () => clearInterval(id);
  }, [token, refreshCount]);

  useEffect(() => {
    if (open && token) loadInbox();
  }, [open, token, loadInbox]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function onItemClick(item: NotificationItem) {
    if (!token) return;
    if (!item.read_at) {
      try {
        await markNotificationRead(token, item.id);
        setUnread((c) => Math.max(0, c - 1));
      } catch {
        /* ignore */
      }
    }
    setOpen(false);
    const url = (item.data?.url as string) || "/notifications";
    window.location.href = url.startsWith("http") ? url : url;
  }

  if (!token) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors"
        aria-label="Notifications"
        aria-expanded={open}
      >
        <Bell className="w-5 h-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-amber-400 text-slate-900 text-[10px] font-bold">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-[420px] overflow-auto bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-xl z-50">
          <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-800 dark:text-slate-200">Notifications</span>
            <Link
              href="/notifications"
              className="text-xs text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300"
              onClick={() => setOpen(false)}
            >
              View all
            </Link>
          </div>
          {loading ? (
            <p className="px-3 py-4 text-sm text-slate-600 dark:text-slate-400">Loading…</p>
          ) : items.length === 0 ? (
            <p className="px-3 py-4 text-sm text-slate-600 dark:text-slate-400">No notifications yet.</p>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onItemClick(item)}
                    className={cn(
                      "w-full text-left px-3 py-2.5 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors",
                      !item.read_at && "bg-slate-100/40 dark:bg-slate-800/40"
                    )}
                  >
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 line-clamp-1">
                      {item.title || item.type}
                    </p>
                    {item.body && (
                      <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 mt-0.5">
                        {item.body}
                      </p>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
