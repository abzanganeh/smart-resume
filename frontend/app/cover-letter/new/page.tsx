"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { CoverLetterPanel } from "@/components/session/CoverLetterPanel";
import { useRequireAuth } from "@/lib/auth/guards";
import { getRecentSessions, trackRecentSession, type RecentSessionEntry } from "@/lib/recentSessions";

function CoverLetterNewContent() {
  const searchParams = useSearchParams();
  const { session, status } = useRequireAuth("/cover-letter/new");
  const [recent, setRecent] = useState<RecentSessionEntry[]>([]);
  const [sessionId, setSessionId] = useState(searchParams.get("session_id") ?? "");
  const [panelOpen, setPanelOpen] = useState(false);

  useEffect(() => {
    setRecent(getRecentSessions());
    const fromQuery = searchParams.get("session_id");
    if (fromQuery) {
      setSessionId(fromQuery);
      setPanelOpen(true);
    }
  }, [searchParams]);

  if (status === "loading" || !session) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        Loading…
      </div>
    );
  }

  const handleSelect = (id: string) => {
    setSessionId(id);
    trackRecentSession(id);
    setPanelOpen(true);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-2xl mx-auto px-6 py-12">
        <h1 className="text-2xl font-bold mb-2">Cover letter</h1>
        <p className="text-slate-400 text-sm mb-8">
          Pick a recent tailoring session, then generate a JD-aligned cover letter from your tailored resume.
        </p>

        {recent.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-slate-400 text-sm">
            No recent sessions yet. Complete a resume tailoring session first, then return here.
          </div>
        ) : (
          <ul className="space-y-2">
            {recent.map((entry) => (
              <li key={entry.session_id}>
                <button
                  type="button"
                  onClick={() => handleSelect(entry.session_id)}
                  className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                    sessionId === entry.session_id
                      ? "border-amber-400/60 bg-amber-400/10"
                      : "border-slate-800 bg-slate-900 hover:border-slate-700"
                  }`}
                >
                  <span className="block text-sm font-medium text-white">{entry.label}</span>
                  <span className="block text-xs text-slate-500 font-mono mt-0.5">{entry.session_id}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {sessionId && !panelOpen && (
          <button
            type="button"
            onClick={() => setPanelOpen(true)}
            className="mt-6 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
          >
            Open cover letter for selected session
          </button>
        )}
      </div>

      {sessionId && (
        <CoverLetterPanel
          sessionId={sessionId}
          accessToken={session.backendAccessToken}
          initial={null}
          open={panelOpen}
          onClose={() => setPanelOpen(false)}
        />
      )}
    </div>
  );
}

export default function CoverLetterNewPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
          Loading…
        </div>
      }
    >
      <CoverLetterNewContent />
    </Suspense>
  );
}
