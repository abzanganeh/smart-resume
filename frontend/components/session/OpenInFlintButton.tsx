"use client";

import { useState } from "react";
import { Copy, ExternalLink } from "lucide-react";

import { ApiError, createFlintHandoff } from "@/lib/api";
import {
  FLINT_DESKTOP_URL,
  FLINT_HANDOFF_ENABLED,
  FLINT_PRODUCT_NAME,
  PRODUCT_NAME,
} from "@/lib/brand";
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
  /** Optional download page when FlintGuide is not installed. */
  flintDownloadUrl?: string;
}

function OpenInFlintComingSoon({
  flintDownloadUrl = FLINT_DESKTOP_URL,
}: Pick<Props, "flintDownloadUrl">) {
  const btnCls =
    "flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-colors";

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        disabled
        aria-disabled="true"
        className={cn(
          btnCls,
          "bg-indigo-600/50 text-white opacity-60 cursor-not-allowed",
        )}
      >
        <ExternalLink className="w-4 h-4" />
        <span>Open in {FLINT_PRODUCT_NAME}</span>
        <span
          className="text-[10px] font-semibold uppercase tracking-wide bg-white/20 text-white px-2 py-0.5 rounded-full"
        >
          Coming soon
        </span>
      </button>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        {FLINT_PRODUCT_NAME} interview prep is launching soon.{" "}
        <a
          href={flintDownloadUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-indigo-700 dark:text-indigo-400 hover:underline"
        >
          Learn more →
        </a>
      </p>
    </div>
  );
}

function OpenInFlintHandoff({
  sessionId,
  disabled = false,
  flintDownloadUrl = FLINT_DESKTOP_URL,
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
        setStatus(`Opening ${FLINT_PRODUCT_NAME}…`);
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
            : `Could not prepare ${FLINT_PRODUCT_NAME} import. Please try again.`;
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
        {loading ? "Preparing…" : `Open in ${FLINT_PRODUCT_NAME}`}
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
              {FLINT_PRODUCT_NAME} did not open automatically (common on Linux dev
              builds). Paste the link below into {FLINT_PRODUCT_NAME} → New Session →
              Import from {PRODUCT_NAME} link.
            </p>
          ) : (
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Import link ready. If {FLINT_PRODUCT_NAME} does not open, paste the link
              there manually.
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
            Don&apos;t have {FLINT_PRODUCT_NAME} yet?{" "}
            <a
              href={flintDownloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-700 dark:text-indigo-400 hover:text-indigo-300 underline"
            >
              Get {FLINT_PRODUCT_NAME}
            </a>
          </p>
        </div>
      )}
    </div>
  );
}

export function OpenInFlintButton(props: Props) {
  if (!FLINT_HANDOFF_ENABLED) {
    return <OpenInFlintComingSoon flintDownloadUrl={props.flintDownloadUrl} />;
  }

  return <OpenInFlintHandoff {...props} />;
}
