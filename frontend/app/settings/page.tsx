"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Loader2, Mail } from "lucide-react";
import { useRequireAuth } from "@/lib/auth/guards";
import { fetchMe, forgotPassword } from "@/lib/auth/api";
import { patchDisplayName, sendEmailVerification } from "@/lib/account";
import { friendlyAuthError } from "@/lib/auth/errors";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const { session, status } = useRequireAuth("/settings");
  const token = session?.backendAccessToken;
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [verified, setVerified] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifySent, setVerifySent] = useState(false);
  const [authProvider, setAuthProvider] = useState("");
  const [resetSent, setResetSent] = useState(false);
  const [resetSending, setResetSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const me = await fetchMe(token);
      setDisplayName(me.display_name);
      setEmail(me.email);
      setVerified(Boolean(me.email_verified_at));
      setAuthProvider(me.auth_provider);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveName() {
    if (!token || !displayName.trim()) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await patchDisplayName(token, displayName.trim());
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function resendVerification() {
    if (!token) return;
    setError(null);
    try {
      await sendEmailVerification(token);
      setVerifySent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send verification");
    }
  }

  if (status === "loading" || !token || loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
      </div>
    );
  }

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link href="/dashboard" className="text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300">
        ← Back to dashboard
      </Link>
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-white mt-4 mb-2">Account settings</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-8">
        Manage your profile, notifications, and data.
      </p>

      {error && (
        <p className="mb-4 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <section className="mb-8 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-4">
        <h2 className="font-medium text-slate-800 dark:text-slate-200">Display name</h2>
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm"
        />
        <button
          type="button"
          onClick={() => void saveName()}
          disabled={saving}
          className={cn(
            "px-4 py-2 rounded-lg text-sm font-medium",
            saving
              ? "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
              : "bg-amber-400 text-slate-900 hover:bg-amber-300",
          )}
        >
          {saving ? "Saving…" : "Save name"}
        </button>
        {saved && (
          <p className="flex items-center gap-1 text-sm text-emerald-700 dark:text-emerald-400">
            <Check className="w-4 h-4" /> Saved
          </p>
        )}
      </section>

      <section className="mb-8 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-3">
        <h2 className="font-medium text-slate-800 dark:text-slate-200">Email</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">{email}</p>
        {verified ? (
          <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
            <Check className="w-4 h-4" /> Verified
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-amber-700 dark:text-amber-300">Email not verified</p>
            <button
              type="button"
              onClick={() => void resendVerification()}
              className="inline-flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300"
            >
              <Mail className="w-4 h-4" />
              {verifySent ? "Verification email sent" : "Send verification email"}
            </button>
          </div>
        )}
      </section>

      <section className="mb-8 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-3">
        <h2 className="font-medium text-slate-800 dark:text-slate-200">Password</h2>
        {authProvider === "email" ? (
          <>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              We will email you a link to choose a new password. The link expires
              in one hour and signs you out of other devices when you use it.
            </p>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setResetSending(true);
                void forgotPassword(email)
                  .then(() => setResetSent(true))
                  .catch((e) =>
                    setError(
                      e instanceof Error
                        ? friendlyAuthError(e.message)
                        : "Could not send reset email",
                    ),
                  )
                  .finally(() => setResetSending(false));
              }}
              disabled={resetSending || resetSent}
              className="inline-flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 disabled:opacity-60"
            >
              {resetSent ? "Reset email sent" : "Email me a password reset link"}
            </button>
          </>
        ) : (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            You sign in with {authProvider || "SSO"}, so there is no password to
            change here.
          </p>
        )}
      </section>

      <section className="mb-8 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
        <h2 className="font-medium text-slate-800 dark:text-slate-200 mb-2">Notifications</h2>
        <Link
          href="/settings/notifications"
          className="text-sm text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300"
        >
          Notification preferences →
        </Link>
      </section>

      <section className="border border-red-200 dark:border-red-900/40 rounded-xl p-4 bg-red-50 dark:bg-red-950/10">
        <h2 className="font-medium text-red-700 dark:text-red-300 mb-2">Danger zone</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
          Download your data or permanently close your account.
        </p>
        <Link
          href="/settings/danger"
          className="text-sm text-red-700 dark:text-red-400 hover:text-red-300 font-medium"
        >
          Open danger zone →
        </Link>
      </section>
    </main>
  );
}
