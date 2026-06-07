"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, BookUser, FileText, Loader2, Mic, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadResumeFile, pasteResumeText, type ParsedResume } from "@/lib/api";
import { uploadProfileResume } from "@/lib/profile";
import { VoiceTab } from "@/components/shared/VoiceTab";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  sessionId: string;
  token?: string; // backend JWT — needed for voice fallback + saved-resume tabs
  onParsed: (parsed: ParsedResume) => void;
  hasMasterResume?: boolean;
  /** Called after the first upload is persisted to the master profile. */
  onMasterResumeSaved?: () => void;
}

type Mode = "upload" | "paste" | "voice" | "saved";

export function ResumeUploader({ sessionId, token, onParsed, hasMasterResume, onMasterResumeSaved }: Props) {
  const [mode, setMode]       = useState<Mode>("upload");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");

  useEffect(() => {
    if (hasMasterResume) {
      setMode("saved");
    }
  }, [hasMasterResume]);

  const persistToMaster = useCallback(
    async (payload: { file?: File; text?: string }) => {
      if (!token || hasMasterResume) return;
      try {
        await uploadProfileResume(token, payload);
        onMasterResumeSaved?.();
      } catch {
        // Session resume is already saved — master sync is best-effort.
      }
    },
    [token, hasMasterResume, onMasterResumeSaved],
  );

  // ── Saved resume state ─────────────────────────────────────────────────────
  const [savedText, setSavedText] = useState<string | null>(null); // null = not loaded
  const [savedLoading, setSavedLoading] = useState(false);

  // ── File upload ────────────────────────────────────────────────────────────
  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (file.size > 5 * 1024 * 1024) { setError("File exceeds 5MB limit."); return; }
      const allowed = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
      ];
      if (!allowed.includes(file.type)) { setError("Only PDF, DOCX, and TXT files are supported."); return; }
      setLoading(true);
      try {
        const result = await uploadResumeFile(sessionId, file);
        await persistToMaster({ file });
        onParsed(result.parsed);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Upload failed.");
      } finally {
        setLoading(false);
      }
    },
    [sessionId, onParsed, persistToMaster],
  );

  // ── Paste ──────────────────────────────────────────────────────────────────
  const handlePaste = async () => {
    if (!pasteText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await pasteResumeText(sessionId, pasteText);
      await persistToMaster({ text: pasteText });
      onParsed(result.parsed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to process resume text.");
    } finally {
      setLoading(false);
    }
  };

  // ── Voice transcript → parse ───────────────────────────────────────────────
  const handleVoiceTranscript = async (text: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await pasteResumeText(sessionId, text);
      await persistToMaster({ text });
      onParsed(result.parsed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to process transcribed resume.");
    } finally {
      setLoading(false);
    }
  };

  // ── Saved resume ───────────────────────────────────────────────────────────
  const loadSavedResume = async () => {
    if (!token) { setSavedText(""); return; }
    setSavedLoading(true);
    setSavedText(null);
    try {
      const res = await fetch(`${BASE}/api/profile/resume`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 404) { setSavedText(""); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { raw_text?: string };
      setSavedText(data.raw_text ?? "");
    } catch {
      setSavedText("");
    } finally {
      setSavedLoading(false);
    }
  };

  const handleModeChange = (m: Mode) => {
    setMode(m);
    setError(null);
    if (m === "saved" && savedText === null) void loadSavedResume();
  };

  const handleUseSaved = async () => {
    if (!savedText?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await pasteResumeText(sessionId, savedText);
      onParsed(result.parsed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to use saved resume.");
    } finally {
      setLoading(false);
    }
  };

  const TABS: { id: Mode; label: string; icon: React.ReactNode; needsToken?: boolean }[] = [
    { id: "upload", label: "Upload file",  icon: <Upload   className="w-3.5 h-3.5" /> },
    { id: "paste",  label: "Paste text",   icon: <FileText className="w-3.5 h-3.5" /> },
    { id: "voice",  label: "Record voice", icon: <Mic      className="w-3.5 h-3.5" /> },
    { id: "saved",  label: "Use saved",    icon: <BookUser className="w-3.5 h-3.5" />, needsToken: true },
  ];

  return (
    <div className="space-y-6">
      {/* Story mode promotional card */}
      {!hasMasterResume && (
        <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 flex items-start gap-3">
          <span className="text-2xl">🎙</span>
          <div className="flex-1 space-y-1">
            <p className="text-white font-medium text-sm">Don&apos;t have a resume file yet?</p>
            <p className="text-slate-400 text-xs">
              Build your master profile by telling your story first — 10–20 minutes of speaking → a complete resume.
            </p>
          </div>
          <a
            href={`/profile?mode=story&return=/session/new`}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 px-3 py-1.5 bg-amber-400 text-slate-900 text-xs font-semibold rounded-lg hover:bg-amber-300 transition-colors"
          >
            Go to Story Mode →
          </a>
        </div>
      )}

      {/* Mode tabs */}
      <div className="flex flex-wrap gap-2">
        {TABS.filter((t) => !t.needsToken || token).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => handleModeChange(t.id)}
            className={cn(
              "px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5",
              mode === t.id
                ? "bg-amber-400 text-slate-900"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700",
            )}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {/* ── Upload ── */}
      {mode === "upload" && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) void handleFile(f); }}
          className={cn(
            "border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors",
            dragging ? "border-amber-400 bg-amber-400/5" : "border-slate-700 hover:border-slate-500",
          )}
          onClick={() => document.getElementById("resume-file-input")?.click()}
        >
          <Upload className="w-10 h-10 text-slate-500 mx-auto mb-3" />
          <p className="text-slate-300 font-medium">Drop your resume here</p>
          <p className="text-slate-500 text-sm mt-1">PDF, DOCX, or TXT · Max 5MB</p>
          <input
            id="resume-file-input" type="file"
            accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }}
          />
        </div>
      )}

      {/* ── Paste ── */}
      {mode === "paste" && (
        <div className="space-y-3">
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="Paste your resume text here…"
            className="w-full h-64 bg-slate-800 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600"
          />
          <div className="flex items-center justify-between">
            <span className="text-slate-500 text-xs">{pasteText.length.toLocaleString()} / 15,000 chars</span>
            <button
              onClick={() => void handlePaste()}
              disabled={!pasteText.trim() || loading}
              className="px-5 py-2 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors text-sm"
            >
              {loading ? "Parsing…" : "Parse resume"}
            </button>
          </div>
        </div>
      )}

      {/* ── Voice — Web Speech API primary (live text, no API key needed);
               MediaRecorder + Whisper fallback for Firefox/Safari ── */}
      {mode === "voice" && (
        <VoiceTab
          token={token}
          submitLabel={loading ? "Parsing…" : "Parse resume"}
          disabled={loading}
          onTranscript={(text) => void handleVoiceTranscript(text)}
        />
      )}

      {/* ── Use saved ── */}
      {mode === "saved" && (
        <div className="space-y-4">
          {savedLoading && (
            <div className="flex items-center gap-2 text-slate-400 text-sm py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading your master resume…
            </div>
          )}
          {!savedLoading && savedText === "" && (
            <div className="text-center py-10 border-2 border-dashed border-slate-700 rounded-xl space-y-3">
              <BookUser className="w-10 h-10 text-slate-600 mx-auto" />
              <p className="text-slate-400 font-medium">No master resume found</p>
              <p className="text-slate-500 text-sm">
                Upload your career history on the{" "}
                <a href="/profile" target="_blank" className="text-amber-400 hover:underline">
                  Profile page
                </a>{" "}
                first, then come back here to reuse it.
              </p>
            </div>
          )}
          {!savedLoading && savedText && (
            <div className="space-y-3">
              <p className="text-slate-400 text-sm">
                Your saved master resume will be used for this session.
                Edit below if needed before parsing.
              </p>
              <textarea
                value={savedText}
                onChange={(e) => setSavedText(e.target.value)}
                disabled={loading}
                rows={12}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-60"
              />
              <div className="flex items-center justify-between">
                <span className="text-slate-500 text-xs">{savedText.length.toLocaleString()} characters</span>
                <button
                  type="button" onClick={() => void handleUseSaved()} disabled={!savedText.trim() || loading}
                  className="px-5 py-2 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors text-sm"
                >
                  {loading ? "Parsing…" : "Use this resume"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          Parsing resume with AI…
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
}
