const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface NotificationItem {
  id: string;
  type: string;
  category: string;
  channel: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  read_at: string | null;
  scheduled_at: string | null;
  sent_at: string | null;
  delivery_status: string;
  created_at: string;
}

export interface NotificationPreferences {
  email_enabled_categories: string[];
  in_app_enabled_categories: string[];
  web_push_enabled: boolean;
  sms_enabled: boolean;
  sms_phone: string | null;
  sms_phone_verified_at: string | null;
  digest_mode: "off" | "daily";
}

async function api<T>(
  path: string,
  token: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`
    );
  }
  return res.json() as Promise<T>;
}

export function fetchUnreadCount(token: string): Promise<{ count: number }> {
  return api("/api/notifications/unread-count", token);
}

export function fetchNotifications(
  token: string,
  params?: { unread_only?: boolean; category?: string; limit?: number }
): Promise<{ items: NotificationItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params?.unread_only) qs.set("unread_only", "true");
  if (params?.category) qs.set("category", params.category);
  if (params?.limit) qs.set("limit", String(params.limit));
  const q = qs.toString();
  return api(`/api/notifications${q ? `?${q}` : ""}`, token);
}

export function markNotificationRead(
  token: string,
  id: string
): Promise<NotificationItem> {
  return api(`/api/notifications/${id}/read`, token, { method: "PATCH" });
}

export function markAllNotificationsRead(
  token: string
): Promise<{ updated: number }> {
  return api("/api/notifications/read-all", token, { method: "PATCH" });
}

export function dismissNotification(
  token: string,
  id: string
): Promise<{ ok: boolean }> {
  return api(`/api/notifications/${id}`, token, { method: "DELETE" });
}

export function fetchNotificationPreferences(
  token: string
): Promise<NotificationPreferences> {
  return api("/api/notifications/preferences", token);
}

export function patchNotificationPreferences(
  token: string,
  body: Partial<NotificationPreferences>
): Promise<NotificationPreferences> {
  return api("/api/notifications/preferences", token, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function sendSmsVerification(
  token: string,
  phone: string
): Promise<{ ok: boolean }> {
  return api("/api/notifications/sms/send-verification", token, {
    method: "POST",
    body: JSON.stringify({ phone }),
  });
}

export function verifySmsCode(
  token: string,
  code: string
): Promise<{ ok: boolean; verified: boolean }> {
  return api("/api/notifications/sms/verify", token, {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export const NOTIFICATION_CATEGORIES = [
  { id: "account_security", label: "Account security" },
  { id: "payment", label: "Payment" },
  { id: "subscription", label: "Subscription" },
  { id: "resume", label: "Resume" },
  { id: "application_follow_up", label: "Application follow-up" },
  { id: "application_interview", label: "Interview reminders" },
  { id: "application_nudge", label: "Application nudges" },
  { id: "application_offer", label: "Offers" },
  { id: "job_alerts", label: "Job alerts" },
  { id: "data_export", label: "Data export" },
  { id: "account_closure", label: "Account closure" },
  { id: "admin_announcement", label: "Announcements" },
] as const;
