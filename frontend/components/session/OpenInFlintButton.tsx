"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";

import { ApiError, createFlintHandoff } from "@/lib/api";
import { cn } from "@/lib/utils";

const FLINT_SCHEME = "flint://import";
const FALLBACK_MS = 3000;

interface Props {
  sessionId: string;
  disabled?: boolean;
  /** Optional download page when Flint is not installed. */
  flintDownloadUrl?: string;
}

function buildDeepLink(token: string): string {
  return `${FLINT_SCHEME}?token=${encodeURIComponent(token)}`;
}

export function OpenInFlintButton({
  sessionId,
  disabled = false,
  flintDownloadUrl = "https://github.com/abzanganeh/flint",
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFallback, setShowFallback] = useState(false);

  const handleOpen = async () => {
    if (disabled || loading) return;
    setError(null);
    setShowFallback(false);
    setLoading(true);
    try {
      const { token } = await createFlintHandoff(sessionId);
      const deepLink = buildDeepLink(token);
      window.location.href = deepLink;
      window.setTimeout(() => {
        if (document.hasFocus()) {
          setShowFallback(true);
        }
      }, FALLBACK_MS);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not prepare Flint import. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const btnCls =
    "flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-colors disabled:opacity-40";

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => void handleOpen()}
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
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
      {showFallback && (
        <p className="text-sm text-slate-400">
          Flint did not open.{" "}
          <a
            href={flintDownloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-400 hover:text-indigo-300 underline"
          >
            Download Flint
          </a>{" "}
          or return here and click again.
        </p>
      )}
    </div>
  );
}
