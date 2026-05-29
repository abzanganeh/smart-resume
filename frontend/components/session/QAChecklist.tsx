"use client";

import { CheckCircle, AlertTriangle, XCircle, AlertCircle } from "lucide-react";
import { type QAOutput, type QAItem } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: QAOutput | null;
  streaming: boolean;
}

const STATUS_CONFIG = {
  pass: { icon: CheckCircle, cls: "text-green-400", bg: "bg-green-400/5 border-green-400/20" },
  warn: { icon: AlertTriangle, cls: "text-amber-400", bg: "bg-amber-400/5 border-amber-400/20" },
  fail: { icon: XCircle, cls: "text-red-400", bg: "bg-red-400/5 border-red-400/20" },
};

function QARow({ item }: { item: QAItem }) {
  const cfg = STATUS_CONFIG[item.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.warn;
  const Icon = cfg.icon;
  return (
    <div className={cn("flex items-start gap-3 border rounded-lg p-3", cfg.bg)}>
      <Icon className={cn("w-4 h-4 shrink-0 mt-0.5", cfg.cls)} />
      <div className="flex-1">
        <p className="text-slate-200 text-sm">{item.item}</p>
        {item.note && <p className={cn("text-xs mt-0.5", cfg.cls)}>{item.note}</p>}
      </div>
    </div>
  );
}

export function QAChecklist({ output, streaming }: Props) {
  if (!output && streaming) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-8">
        <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        Running quality assurance checklist…
      </div>
    );
  }
  if (!output) return null;

  // Guard: LLM may return a status value not in our map
  const overallCfg = STATUS_CONFIG[output.overall_status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.warn;
  const OverallIcon = overallCfg.icon;

  return (
    <div className="space-y-4">
      {/* Overall status */}
      <div className={cn("flex items-center gap-3 rounded-xl p-4 border", overallCfg.bg)}>
        <OverallIcon className={cn("w-6 h-6", overallCfg.cls)} />
        <div>
          <p className={cn("font-semibold", overallCfg.cls)}>
            Overall:{" "}
            {output.overall_status
              ? output.overall_status.charAt(0).toUpperCase() + output.overall_status.slice(1)
              : "Unknown"}
          </p>
          {output.overall_status === "pass" && (
            <p className="text-green-400/70 text-sm">Your resume passes all quality checks. Ready to export.</p>
          )}
        </div>
      </div>

      {/* Checklist items */}
      <div className="space-y-2">
        {(output.checklist ?? []).map((item, i) => {
        const status = STATUS_CONFIG[item.status as keyof typeof STATUS_CONFIG] ? item.status : "warn";
        return <QARow key={i} item={{ ...item, status: status as QAItem["status"] }} />;
      })}
      </div>

      {/* User action required */}
      {(output.user_action_required ?? []).length > 0 && (
        <div className="bg-red-400/10 border border-red-400/20 rounded-xl p-4">
          <div className="flex items-center gap-2 text-red-400 font-semibold text-sm mb-2">
            <AlertCircle className="w-4 h-4" />
            Action required before export
          </div>
          <ul className="space-y-1">
            {(output.user_action_required ?? []).map((action, i) => (
              <li key={i} className="text-red-300 text-sm flex items-start gap-2">
                <span className="mt-1">›</span>
                {action}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
