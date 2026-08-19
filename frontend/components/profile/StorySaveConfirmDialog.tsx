"use client";

import { Loader2, Save } from "lucide-react";

interface Props {
  open: boolean;
  saveCreditLabel: string;
  reviewCount: number;
  saving: boolean;
  attestationChecked: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function StorySaveConfirmDialog({
  open,
  saveCreditLabel,
  reviewCount,
  saving,
  attestationChecked,
  onClose,
  onConfirm,
}: Props) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="story-save-title"
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl p-6 space-y-4">
        <div>
          <h2 id="story-save-title" className="text-lg font-semibold text-slate-900 dark:text-white">
            Save to your profile?
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">
            This replaces your master resume with the reviewed draft.
            {reviewCount > 0 && (
              <> You still have {reviewCount} item{reviewCount === 1 ? "" : "s"} flagged for review.</>
            )}
          </p>
        </div>

        <div className="rounded-lg bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm text-slate-700 dark:text-slate-300">
          Cost: <strong>{saveCreditLabel}</strong>
        </div>

        {!attestationChecked && (
          <p className="text-xs text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 border border-amber-400/30 rounded-lg px-3 py-2">
            Check the attestation box on the review screen before saving.
          </p>
        )}

        <div className="flex gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="flex-1 py-2.5 border border-slate-300 dark:border-slate-700 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
          >
            Go back and edit
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={saving || !attestationChecked}
            className="flex-1 py-2.5 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving…
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Save to profile
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
