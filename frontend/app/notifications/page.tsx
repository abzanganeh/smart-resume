"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, X } from "lucide-react";
import { useRequireAuth } from "@/lib/auth/guards";
import {
  dismissNotification,
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NOTIFICATION_CATEGORIES,
  type NotificationItem,
} from "@/lib/notifications";
import { cn } from "@/lib/utils";

type Tab = "all" | "unread" | string;

export default function NotificationsPage() {
  const { session, status } = useRequireAuth("/notifications");
  const token = session?.backendAccessToken;
  const [tab, setTab] = useState<Tab>("all");
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params =
        tab === "unread"
          ? { unread_only: true, limit: 100 }
          : tab === "all"
            ? { limit: 100 }
            : { category: tab, limit: 100 };
      const { items: list } = await fetchNotifications(token, params);
      setItems(list);
    } finally {
      setLoading(false);
    }
  }, [token, tab]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRead(item: NotificationItem) {
    if (!token || item.read_at) return;
    await markNotificationRead(token, item.id);
    await load();
  }

  async function handleDismiss(id: string) {
    if (!token) return;
    await dismissNotification(token, id);
    await load();
  }

  async function handleMarkAll() {
    if (!token) return;
    await markAllNotificationsRead(token);
    await load();
  }

  if (status === "loading" || !token) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Notifications</h1>
          <p className="text-sm text-slate-500 mt-1">
            <Link href="/settings/notifications" className="text-amber-400 hover:underline">
              Notification settings
            </Link>
          </p>
        </div>
        <button
          type="button"
          onClick={handleMarkAll}
          className="text-sm text-amber-400 hover:text-amber-300"
        >
          Mark all read
        </button>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {(["all", "unread"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm capitalize",
              tab === t
                ? "bg-amber-400/20 text-amber-300 border border-amber-400/40"
                : "bg-slate-800 text-slate-400 hover:text-slate-200"
            )}
          >
            {t}
          </button>
        ))}
        {NOTIFICATION_CATEGORIES.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setTab(c.id)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm",
              tab === c.id
                ? "bg-amber-400/20 text-amber-300 border border-amber-400/40"
                : "bg-slate-800 text-slate-400 hover:text-slate-200"
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-amber-400" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-slate-500 text-center py-12">No notifications in this view.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className={cn(
                "border border-slate-800 rounded-xl p-4 flex gap-3",
                !item.read_at && "bg-slate-900/80"
              )}
            >
              <button
                type="button"
                className="flex-1 text-left min-w-0"
                onClick={() => handleRead(item)}
              >
                <p className="font-medium text-slate-200">{item.title || item.type}</p>
                {item.body && (
                  <p className="text-sm text-slate-500 mt-1">{item.body}</p>
                )}
                <p className="text-xs text-slate-600 mt-2">
                  {new Date(item.created_at).toLocaleString()}
                </p>
              </button>
              <button
                type="button"
                onClick={() => handleDismiss(item.id)}
                className="shrink-0 p-1 text-slate-500 hover:text-slate-300"
                aria-label="Dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
