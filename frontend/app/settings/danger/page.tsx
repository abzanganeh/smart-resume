"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Download, Loader2 } from "lucide-react";
import { useRequireAuth } from "@/lib/auth/guards";
import { fetchMe } from "@/lib/auth/api";
import {
  cancelAccountClosure,
  closeAccount,
  pollExportUntilReady,
  startExport,
} from "@/lib/account";
import { cn } from "@/lib/utils";

export default function DangerZonePage() {
  const { session, status } = useRequireAuth("/settings/danger");
  const token = session?.backendAccessToken;

  const [closureDate, setClosureDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportBusy, setExportBusy] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [closeStep, setCloseStep] = useState<"prompt" | "confirm">("prompt");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [closeBusy, setCloseBusy] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const me = await fetchMe(token);
      if (me.closure_requested_at) {
        const requested = new Date(me.closure_requested_at);
        const scheduled = new Date(requested);
        scheduled.setDate(scheduled.getDate() + 30);
        setClosureDate(scheduled.toISOString());
      } else {
        setClosureDate(null);
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleExport(): Promise<boolean> {
    if (!token) return false;
    setExportBusy(true);
    setError(null);
    setDownloadUrl(null);
    try {
      const { job_id } = await startExport(token);
      const { promise } = pollExportUntilReady(token, job_id);
      const job = await promise;
      if (job.presigned_url) {
        setDownloadUrl(job.presigned_url);
        return true;
      }
      setError("Export completed but no download URL was returned.");
      return false;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
      return false;
    } finally {
      setExportBusy(false);
    }
  }

  async function handleClose(skipExport: boolean) {
    if (!token) return;
    if (!skipExport) {
      const ok = await handleExport();
      if (!ok) return;
      setCloseStep("confirm");
      return;
    }
    setCloseStep("confirm");
  }

  async function confirmClose() {
    if (!token || deleteConfirm !== "DELETE") return;
    setCloseBusy(true);
    setError(null);
    try {
      const res = await closeAccount(token);
      setClosureDate(res.scheduled_delete_at);
      setShowCloseDialog(false);
      setDeleteConfirm("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not schedule closure");
    } finally {
      setCloseBusy(false);
    }
  }

  async function handleCancelClosure() {
    if (!token) return;
    setCancelBusy(true);
    setError(null);
    try {
      await cancelAccountClosure(token);
      setClosureDate(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not cancel closure");
    } finally {
      setCancelBusy(false);
    }
  }

  if (status === "loading" || !token || loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
      </div>
    );
  }

  const formattedClosure = closureDate
    ? new Date(closureDate).toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link href="/settings" className="text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300">
        ← Account settings
      </Link>
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-white mt-4 mb-2 flex items-center gap-2">
        <AlertTriangle className="w-6 h-6 text-red-700 dark:text-red-400" />
        Danger zone
      </h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-8">
        Export your data or permanently delete your account after a 30-day grace period.
      </p>

      {closureDate && formattedClosure && (
        <div
          className="mb-6 rounded-xl border border-amber-500/40 bg-amber-50 dark:bg-amber-950/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-200"
          data-testid="closure-banner"
        >
          Account will be deleted on {formattedClosure}.
          <button
            type="button"
            onClick={() => void handleCancelClosure()}
            disabled={cancelBusy}
            className="ml-3 underline hover:text-amber-100 disabled:opacity-50"
          >
            {cancelBusy ? "Cancelling…" : "Cancel closure"}
          </button>
        </div>
      )}

      {error && (
        <p className="mb-4 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <section className="mb-8 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-4">
        <h2 className="font-medium text-slate-800 dark:text-slate-200">Download my data</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Request a ZIP of your resumes, applications, saved jobs, and account info.
          Limited to 2 exports per 24 hours.
        </p>
        <button
          type="button"
          onClick={() => void handleExport()}
          disabled={exportBusy}
          className={cn(
            "inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium",
            exportBusy
              ? "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
              : "bg-slate-200 text-slate-900 hover:bg-white",
          )}
        >
          {exportBusy ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Preparing export…
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              Download my data
            </>
          )}
        </button>
        {downloadUrl && (
          <a
            href={downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400 hover:text-emerald-300"
            data-testid="export-download-link"
          >
            <Download className="w-4 h-4" />
            Download ZIP (link valid 24h)
          </a>
        )}
      </section>

      <section className="border border-red-200 dark:border-red-900/50 rounded-xl p-4 bg-red-50 dark:bg-red-950/10 space-y-4">
        <h2 className="font-medium text-red-700 dark:text-red-300">Close account</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Your account enters a 30-day grace period. You can cancel anytime before deletion.
        </p>
        {!closureDate && (
          <button
            type="button"
            onClick={() => {
              setShowCloseDialog(true);
              setCloseStep("prompt");
            }}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-500"
          >
            Close my account
          </button>
        )}
      </section>

      {showCloseDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div
            className="w-full max-w-md rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 space-y-4"
            role="dialog"
            aria-modal="true"
          >
            {closeStep === "prompt" ? (
              <>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Download your data first?</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  We recommend exporting your data before closing your account.
                </p>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => void handleClose(false)}
                    className="px-4 py-2 rounded-lg text-sm bg-amber-400 text-slate-900 font-medium"
                  >
                    Yes, export first
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleClose(true)}
                    className="px-4 py-2 rounded-lg text-sm border border-slate-400 dark:border-slate-600 text-slate-700 dark:text-slate-300"
                  >
                    Skip export
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCloseDialog(false)}
                    className="px-4 py-2 rounded-lg text-sm text-slate-600 dark:text-slate-400"
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Confirm account closure</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Type <strong className="text-red-700 dark:text-red-400">DELETE</strong> to schedule deletion in
                  30 days.
                </p>
                <input
                  type="text"
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  placeholder="DELETE"
                  className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm"
                  data-testid="delete-confirm-input"
                />
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => void confirmClose()}
                    disabled={deleteConfirm !== "DELETE" || closeBusy}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 text-white disabled:opacity-40"
                  >
                    {closeBusy ? "Scheduling…" : "Schedule deletion"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCloseDialog(false)}
                    className="px-4 py-2 rounded-lg text-sm text-slate-600 dark:text-slate-400"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
