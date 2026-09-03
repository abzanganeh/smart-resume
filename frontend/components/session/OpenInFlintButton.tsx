"use client";

import { useState } from "react";
import { Copy, ExternalLink } from "lucide-react";

import { ApiError, createFlintHandoff } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import {
  buildFlintImportLink,
  FLINT_OPEN_FALLBACK_MS,
  navigateFlintImportCarrier,
  openFlintImportCarrier,
} from "@/lib/flintDeepLink";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
  disabled?: boolean;
  /** Optional download page when Flint is not installed. */
  flintDownloadUrl?: string;
}

export function OpenInFlintButton({
  sessionId,
  disabled = false,
  flintDownloadUrl = "https://github.com/abzanganeh/flint",
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [handoffReady, setHandoffReady] = useState(false);
  const [showAutoOpenHint, setShowAutoOpenHint] = useState(false);
  const [lastDeepLink, setLastDeepLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleOpen = () => {
    if (disabled || loading) return;
    setError(null);
    setHandoffReady(false);
    setShowAutoOpenHint(false);
    setCopied(false);
    setStatus("Preparing import link…");

    // Must happen synchronously in the click handler — async breaks custom-scheme launch.
    const carrier = openFlintImportCarrier();
    if (!carrier) {
      setError(
        "Popup blocked — allow popups for this site, or use Copy import link after handoff.",
      );
    }
    setLoading(true);

    void (async () => {
      try {
        const { token } = await createFlintHandoff(sessionId);
        const deepLink = buildFlintImportLink(token);
        setLastDeepLink(deepLink);
        setHandoffReady(true);
        setStatus("Opening Flint…");
        const launched = navigateFlintImportCarrier(carrier, deepLink);
        window.setTimeout(() => {
          if (document.hasFocus() || !launched) {
            setShowAutoOpenHint(true);
            setStatus(null);
          }
        }, FLINT_OPEN_FALLBACK_MS);
      } catch (err) {
        carrier?.close();
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not prepare Flint import. Please try again.";
        setError(message);
        setStatus(null);
        setHandoffReady(false);
      } finally {
        setLoading(false);
      }
    })();
  };

  const copyDeepLink = async () => {
    if (!lastDeepLink) return;
    try {
      await navigator.clipboard.writeText(lastDeepLink);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const btnCls =
    "flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-colors disabled:opacity-40";

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={handleOpen}
        disabled={disabled || loading}
        className={cn(
          btnCls,
          "bg-indigo-600 text-white hover:bg-indigo-500",
          (disabled || loading) && "opacity-40 cursor-not-allowed",
        )}
      >
        <ExternalLink className="w-4 h-4" />
        {loading ? "Preparing…" : "Open in Flint"}
      </button>
      {status && (
        <p className="text-sm text-slate-600 dark:text-slate-400" role="status" aria-live="polite">
          {status}
        </p>
      )}
      {error && (
        <p className="text-sm text-red-700 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
      {handoffReady && lastDeepLink && (
        <div className="rounded-lg border border-indigo-500/40 bg-indigo-50 dark:bg-indigo-950/30 p-3 space-y-2">
          {showAutoOpenHint ? (
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Flint did not open automatically (common on Linux dev builds). Paste the
              link below into Flint → New Session → Import from {PRODUCT_NAME} link.
            </p>
          ) : (
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Import link ready. If Flint does not open, paste the link there manually.
            </p>
          )}
          <button
            type="button"
            onClick={() => void copyDeepLink()}
            className="flex items-center gap-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-300 hover:text-indigo-200 transition-colors"
          >
            <Copy className="w-3.5 h-3.5" />
            {copied ? "Link copied" : "Copy import link"}
          </button>
          <p className="text-xs text-slate-600 dark:text-slate-400 break-all font-mono">{lastDeepLink}</p>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Don&apos;t have Flint yet?{" "}
            <a
              href={flintDownloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-700 dark:text-indigo-400 hover:text-indigo-300 underline"
            >
              Download Flint
            </a>
          </p>
        </div>
      )}
    </div>
  );
}
