"use client";

import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { getVersions, type ResumeVersionMeta } from "@/lib/api";

interface Props {
  sessionId: string;
  currentVersion: number;
  onRestore: (snapshotId: string) => void;
}

export function VersionHistory({ sessionId, currentVersion, onRestore }: Props) {
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState<ResumeVersionMeta[]>([]);

  const load = async () => {
    try {
      const r = await getVersions(sessionId);
      setVersions(r.versions);
    } catch {}
  };

  useEffect(() => {
    if (open) load();
  }, [open, currentVersion]);

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 text-xs transition-colors"
      >
        <History className="w-3.5 h-3.5" />
        Version history ({currentVersion})
      </button>
      {open && (
        <div className="mt-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
          {versions.length === 0 ? (
            <p className="text-slate-600 dark:text-slate-400 text-xs p-3">No versions saved yet.</p>
          ) : (
            versions.map((v) => (
              <div key={v.snapshot_id} className="flex items-center justify-between p-3 border-b border-slate-200 dark:border-slate-800 last:border-0">
                <div>
                  <p className="text-slate-700 dark:text-slate-300 text-xs font-medium">v{v.version} — {v.label}</p>
                  <p className="text-slate-600 dark:text-slate-400 text-xs">{new Date(v.created_at).toLocaleString()}</p>
                </div>
                {v.version !== currentVersion && (
                  <button
                    onClick={() => onRestore(v.snapshot_id)}
                    className="text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 text-xs font-medium"
                  >
                    Restore
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
