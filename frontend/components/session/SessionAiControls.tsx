"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Key, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getAiMode,
  getStoredKey,
  setAiMode,
  subscribeByokChanges,
  type AiMode,
} from "@/lib/keyStore";
import ProviderSetup from "@/components/wizard/ProviderSetup";
import {
  LLMTierSelector,
} from "@/components/session/LLMTierSelector";
import type { LLMTier, LLMUpgradeStatus } from "@/lib/api";

interface Props {
  llmTier: LLMTier;
  llmStatus: LLMUpgradeStatus | null;
  phaseRunning: boolean;
  showTierSelector: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onLlmTierChange: (tier: LLMTier) => void;
  onRequestPurchase: (tier: Exclude<LLMTier, "standard">) => void;
}

export function SessionAiControls({
  llmTier,
  llmStatus,
  phaseRunning,
  showTierSelector,
  open,
  onOpenChange,
  onLlmTierChange,
  onRequestPurchase,
}: Props) {
  const [mode, setMode] = useState<AiMode>("platform");
  const [byokEntry, setByokEntry] = useState<ReturnType<typeof getStoredKey>>(null);

  useEffect(() => {
    function refresh() {
      setMode(getAiMode());
      setByokEntry(getStoredKey());
    }
    refresh();
    return subscribeByokChanges(refresh);
  }, []);

  const summary =
    mode === "platform"
      ? `Platform AI · ${llmTier.charAt(0).toUpperCase()}${llmTier.slice(1)} tier`
      : byokEntry?.apiKey
        ? `Your key · ${byokEntry.provider}${byokEntry.model ? ` / ${byokEntry.model}` : ""}`
        : "Your API key · not configured";

  return (
    <div className="mb-6 rounded-xl border border-slate-700 bg-slate-800/40 overflow-hidden">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-800/80 transition-colors"
      >
        <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">AI for this session</p>
          <p className="text-sm text-slate-200 truncate">{summary}</p>
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-slate-700 space-y-4">
          <p className="text-xs text-slate-500">
            Change provider or switch to Platform AI without starting a new session. Applies to the next step you run.
          </p>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setAiMode("platform")}
              className={cn(
                "px-3 py-2 rounded-lg text-xs font-semibold border transition-colors",
                mode === "platform"
                  ? "bg-amber-400/15 border-amber-400/50 text-amber-300"
                  : "border-slate-600 text-slate-400 hover:border-slate-500",
              )}
            >
              Platform AI (credits)
            </button>
            <button
              type="button"
              onClick={() => setAiMode("byok")}
              className={cn(
                "px-3 py-2 rounded-lg text-xs font-semibold border transition-colors flex items-center gap-1.5",
                mode === "byok"
                  ? "bg-violet-500/15 border-violet-500/50 text-violet-300"
                  : "border-slate-600 text-slate-400 hover:border-slate-500",
              )}
            >
              <Key className="w-3.5 h-3.5" />
              My API key (BYOK)
            </button>
          </div>

          {mode === "platform" && showTierSelector && (
            <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-3">
              <p className="text-xs text-slate-400 mb-3">
                Uses Smart Resume credits. Standard is included; Better and Best use upgrade packs.
              </p>
              <LLMTierSelector
                value={llmTier}
                status={llmStatus}
                disabled={phaseRunning}
                onChange={onLlmTierChange}
                onRequestPurchase={onRequestPurchase}
              />
            </div>
          )}

          {mode === "platform" && !showTierSelector && (
            <p className="text-xs text-slate-500 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
              Sign in to use Platform AI tiers. Anonymous sessions use the server default model.
            </p>
          )}

          {mode === "byok" && (
            <ProviderSetup
              inline
              onComplete={() => {
                setByokEntry(getStoredKey());
                setMode("byok");
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
