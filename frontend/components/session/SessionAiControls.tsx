"use client";

import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
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
  const summary = `Platform AI · ${llmTier.charAt(0).toUpperCase()}${llmTier.slice(1)} tier`;

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
            Smart Resume runs the AI for you using your subscription tier and credits.
          </p>

          {showTierSelector && (
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

          {!showTierSelector && (
            <p className="text-xs text-slate-500 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
              Sign in to use Platform AI tiers. Anonymous sessions use the server default model.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
