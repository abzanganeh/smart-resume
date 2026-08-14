"use client";

import { Mic, MicOff } from "lucide-react";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  /** Called with the final transcript text so the parent can submit it. */
  onTranscript: (text: string) => void;
  /** Backend JWT — needed to call the Whisper fallback endpoint. */
  token?: string;
  /** Label for the submit button shown in preview mode. */
  submitLabel?: string;
  /** Whether the parent is busy (loading). Disables start button. */
  disabled?: boolean;
}

/**
 * Reusable voice-recording UI.
 *
 * • Primary path (Chrome / Edge)  — Web Speech API, live text, no API key.
 * • Fallback path (Firefox/Safari) — MediaRecorder → Whisper endpoint.
 */
export function VoiceTab({
  onTranscript,
  token,
  submitLabel = "Use this text",
  disabled = false,
}: Props) {
  const { voiceState, finalText, setFinalText, interimText, durationLabel,
          error, setError, supportsWebSpeech, start, stop, reset } =
    useVoiceRecorder({
      onBlob: async (blob) => {
        // Fallback: send to OpenAI Whisper via the backend endpoint.
        const ext = blob.type.includes("ogg") ? "ogg"
          : blob.type.includes("mp4") ? "mp4" : "webm";
        const form = new FormData();
        form.append("audio", blob, `recording.${ext}`);
        const headers: Record<string, string> = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const res = await fetch(`${BASE}/api/profile/resume/transcribe`, {
          method: "POST", headers, body: form,
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({})) as { detail?: string };
          throw new Error(body.detail ?? `HTTP ${res.status}`);
        }
        const data = await res.json() as { text: string };
        setFinalText(data.text);
      },
    });

  const handleStart = async () => {
    setError(null);
    await start();
  };

  const handleStop = async () => { await stop(); };

  const handleSubmit = () => {
    if (finalText.trim()) onTranscript(finalText.trim());
  };

  // ── Idle ───────────────────────────────────────────────────────────────────
  if (voiceState === "idle") {
    return (
      <div className="flex flex-col items-center gap-4 py-10 border-2 border-dashed border-slate-700 rounded-xl">
        <Mic className="w-10 h-10 text-slate-500" />
        <p className="text-slate-300 font-medium">Record your resume by voice</p>
        <p className="text-slate-500 text-sm text-center max-w-xs">
          {supportsWebSpeech
            ? "Speak naturally — your words appear live. No API key needed."
            : "Record audio, then we'll transcribe it using Whisper."}
        </p>
        {!supportsWebSpeech && (
          <p className="text-slate-600 text-xs text-center">
            Live transcription requires Chrome or Edge.
            Fallback requires an OpenAI API key.
          </p>
        )}
        <button
          type="button"
          onClick={() => void handleStart()}
          disabled={disabled}
          className="mt-2 px-6 py-3 bg-red-500 hover:bg-red-400 text-white font-semibold rounded-full transition-colors flex items-center gap-2 disabled:opacity-40"
        >
          <Mic className="w-4 h-4" /> Start recording
        </button>
        {error && (
          <p className="text-red-400 text-sm text-center px-4">{error}</p>
        )}
      </div>
    );
  }

  // ── Speaking (Web Speech API live mode) ────────────────────────────────────
  if (voiceState === "speaking") {
    return (
      <div className="space-y-3">
        {/* Live indicator */}
        <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
          </span>
          <span className="text-red-400 font-medium text-sm">
            Listening · {durationLabel}
          </span>
          <button
            type="button"
            onClick={() => void handleStop()}
            className="ml-auto px-4 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold rounded-full transition-colors"
          >
            Stop
          </button>
        </div>

        {/* Live transcript box */}
        <div className="min-h-32 bg-slate-800/60 border border-slate-700 rounded-xl p-4 text-sm leading-relaxed">
          {finalText || interimText ? (
            <>
              <span className="text-slate-200">{finalText}</span>
              {finalText && interimText && " "}
              {interimText && (
                <span className="text-slate-500 italic">{interimText}</span>
              )}
            </>
          ) : (
            <span className="text-slate-600 italic">Start speaking — your words appear here…</span>
          )}
        </div>
        {error && <p className="text-red-400 text-sm">{error}</p>}
      </div>
    );
  }

  // ── Recording (MediaRecorder fallback — no live text) ──────────────────────
  if (voiceState === "recording") {
    return (
      <div className="flex flex-col items-center gap-4 py-10 border-2 border-dashed border-slate-700 rounded-xl">
        <div className="relative flex items-center justify-center">
          <span className="absolute inline-flex h-16 w-16 rounded-full bg-red-500 opacity-30 animate-ping" />
          <div className="relative w-16 h-16 rounded-full bg-red-500 flex items-center justify-center">
            <MicOff className="w-7 h-7 text-white" />
          </div>
        </div>
        <p className="text-red-400 font-semibold tabular-nums text-lg">{durationLabel}</p>
        <p className="text-slate-400 text-sm">Recording… speak your career history</p>
        <button
          type="button"
          onClick={() => void handleStop()}
          className="px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-full transition-colors flex items-center gap-2"
        >
          Stop &amp; transcribe
        </button>
      </div>
    );
  }

  // ── Transcribing (Whisper in progress) ────────────────────────────────────
  if (voiceState === "transcribing") {
    return (
      <div className="flex flex-col items-center gap-3 py-12 border-2 border-dashed border-slate-700 rounded-xl">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-300 text-sm">Transcribing with Whisper…</p>
      </div>
    );
  }

  // ── Preview / edit ─────────────────────────────────────────────────────────
  return (
    <div className="space-y-3">
      <p className="text-slate-400 text-sm">Review and edit, then continue.</p>
      <textarea
        value={finalText}
        onChange={(e) => setFinalText(e.target.value)}
        disabled={disabled}
        rows={10}
        className="w-full bg-slate-800 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-60"
      />
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={reset}
          disabled={disabled}
          className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-sm font-medium disabled:opacity-40 flex items-center gap-1.5"
        >
          <Mic className="w-3.5 h-3.5" /> Record again
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!finalText.trim() || disabled}
          className="px-5 py-2 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors text-sm"
        >
          {submitLabel}
        </button>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
    </div>
  );
}
