"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Loader2 } from "lucide-react";
import { useRequireAuth } from "@/lib/auth/guards";
import {
  fetchNotificationPreferences,
  NOTIFICATION_CATEGORIES,
  patchNotificationPreferences,
  sendSmsVerification,
  verifySmsCode,
  type NotificationPreferences,
} from "@/lib/notifications";
import { registerWebPush } from "@/lib/notifications/web-push";
import { cn } from "@/lib/utils";

export default function NotificationSettingsPage() {
  const { session, status } = useRequireAuth("/settings/notifications");
  const token = session?.backendAccessToken;
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [phone, setPhone] = useState("");
  const [smsCode, setSmsCode] = useState("");
  const [smsStep, setSmsStep] = useState<"idle" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const p = await fetchNotificationPreferences(token);
      setPrefs(p);
      if (p.sms_phone) setPhone(p.sms_phone);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(patch: Partial<NotificationPreferences>) {
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await patchNotificationPreferences(token, patch);
      setPrefs(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function toggleCategory(
    channel: "email_enabled_categories" | "in_app_enabled_categories",
    categoryId: string
  ) {
    if (!prefs) return;
    const list = [...(prefs[channel] ?? [])];
    const idx = list.indexOf(categoryId);
    if (idx >= 0) list.splice(idx, 1);
    else list.push(categoryId);
    const next = { ...prefs, [channel]: list };
    setPrefs(next);
    save({ [channel]: list });
  }

  async function enablePush() {
    if (!token) return;
    setPushBusy(true);
    setError(null);
    try {
      const ok = await registerWebPush(token);
      if (ok) await save({ web_push_enabled: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Web push failed");
    } finally {
      setPushBusy(false);
    }
  }

  async function sendSms() {
    if (!token || !phone.trim()) return;
    setError(null);
    try {
      await sendSmsVerification(token, phone.trim());
      setSmsStep("sent");
    } catch (e) {
      setError(e instanceof Error ? e.message : "SMS send failed");
    }
  }

  async function confirmSms() {
    if (!token) return;
    setError(null);
    try {
      await verifySmsCode(token, smsCode.trim());
      await load();
      setSmsStep("idle");
      setSmsCode("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid code");
    }
  }

  if (status === "loading" || !token || loading || !prefs) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
      </div>
    );
  }

  const smsVerified = Boolean(prefs.sms_phone_verified_at);

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link href="/notifications" className="text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300">
        ← Back to inbox
      </Link>
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-white mt-4 mb-2">Notification preferences</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-8">
        Choose how we reach you for each category. SMS is limited to interview reminders.
      </p>

      {error && (
        <p className="mb-4 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <section className="mb-10 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 bg-white/80 dark:bg-slate-900/80 border-b border-slate-200 dark:border-slate-800">
          <h2 className="font-medium text-slate-800 dark:text-slate-200">Email & in-app</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-600 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2 text-center">Email</th>
                <th className="px-4 py-2 text-center">In-app</th>
              </tr>
            </thead>
            <tbody>
              {NOTIFICATION_CATEGORIES.map((c) => (
                <tr key={c.id} className="border-b border-slate-200 dark:border-slate-800/60">
                  <td className="px-4 py-2.5 text-slate-700 dark:text-slate-300">{c.label}</td>
                  <td className="px-4 py-2.5 text-center">
                    <input
                      type="checkbox"
                      checked={prefs.email_enabled_categories.includes(c.id)}
                      onChange={() =>
                        toggleCategory("email_enabled_categories", c.id)
                      }
                      disabled={saving}
                      className="rounded border-slate-400 dark:border-slate-600"
                    />
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    <input
                      type="checkbox"
                      checked={prefs.in_app_enabled_categories.includes(c.id)}
                      onChange={() =>
                        toggleCategory("in_app_enabled_categories", c.id)
                      }
                      disabled={saving}
                      className="rounded border-slate-400 dark:border-slate-600"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-10 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <h2 className="font-medium text-slate-800 dark:text-slate-200 mb-2">Browser notifications</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Optional web push alerts when you are not on the site.
        </p>
        <button
          type="button"
          onClick={enablePush}
          disabled={pushBusy || prefs.web_push_enabled}
          className={cn(
            "px-4 py-2 rounded-lg text-sm font-medium",
            prefs.web_push_enabled
              ? "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 cursor-default"
              : "bg-amber-400 text-slate-900 hover:bg-amber-300"
          )}
        >
          {prefs.web_push_enabled
            ? "Browser notifications enabled"
            : pushBusy
              ? "Enabling…"
              : "Enable browser notifications"}
        </button>
      </section>

      <section className="mb-10 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <h2 className="font-medium text-slate-800 dark:text-slate-200 mb-2">SMS (interview reminders)</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Verify your phone to receive interview reminder texts.
        </p>
        {smsVerified ? (
          <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
            <Check className="w-4 h-4" />
            Verified {prefs.sms_phone}
          </p>
        ) : (
          <div className="space-y-3">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+15551234567"
              className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm"
            />
            {smsStep === "idle" ? (
              <button
                type="button"
                onClick={sendSms}
                className="text-sm text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300"
              >
                Send verification code
              </button>
            ) : (
              <>
                <input
                  type="text"
                  value={smsCode}
                  onChange={(e) => setSmsCode(e.target.value)}
                  placeholder="6-digit code"
                  className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm"
                />
                <button
                  type="button"
                  onClick={confirmSms}
                  className="px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-medium hover:bg-amber-300"
                >
                  Verify code
                </button>
              </>
            )}
          </div>
        )}
      </section>

      <section className="border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <h2 className="font-medium text-slate-800 dark:text-slate-200 mb-2">Digest mode</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Batch non-urgent emails into one daily digest.
        </p>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={prefs.digest_mode === "daily"}
            onChange={(e) =>
              save({ digest_mode: e.target.checked ? "daily" : "off" })
            }
            disabled={saving}
            className="rounded border-slate-400 dark:border-slate-600"
          />
          Daily digest
        </label>
      </section>
    </main>
  );
}
