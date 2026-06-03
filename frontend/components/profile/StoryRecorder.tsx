"use client";

/**
 * StoryRecorder — segmented voice story recording UI.
 *
 * Max 30 segments × 60 seconds = 30 min.
 * Each segment is editable after recording.
 * "Generate resume from story" calls POST /api/profile/resume/from-story.
 *
 * Credit path:
 *   - Web Speech (Chrome/Edge): 0 credits
 *   - Whisper fallback (Firefox/Safari): 2 credits — shown in disclosure before start
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, Clock, Loader2, Mic, RotateCcw, Send, Sparkles, Wand2 } from "lucide-react";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { StorySegment } from "./StorySegment";
import { polishResume, submitStory } from "@/lib/story";
import { getStoredKey } from "@/lib/keyStore";
import { cn } from "@/lib/utils";

const MAX_SEGMENTS = 30;
const SEGMENT_DURATION_MS = 60_000;
const WARN_TOTAL_MS = 18 * 60 * 1000;
const MAX_TOTAL_MS  = 30 * 60 * 1000;

interface Props {
  token: string;
  onSaved: () => void;
}

type RecordingState = "idle" | "recording" | "re-recording";

export function StoryRecorder({ token, onSaved }: Props) {
  const [segments, setSegments] = useState<string[]>([]);
  const [recordingState, setRecordingState]     = useState<RecordingState>("idle");
  const [reRecordingIndex, setReRecordingIndex] = useState<number | null>(null);
  const [totalMs, setTotalMs] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewText, setReviewText] = useState<string | null>(null);
  const [prevText, setPrevText] = useState<string | null>(null);
  const [polishInstruction, setPolishInstruction] = useState("");
  const [polishing, setPolishing] = useState(false);
  const [polishError, setPolishError] = useState<string | null>(null);
  const polishInputRef = useRef<HTMLTextAreaElement>(null);

  const totalTimerRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const totalStartRef  = useRef<number>(0);
  const segmentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { voiceState, finalText, interimText, durationLabel, supportsWebSpeech,
          start, stop, reset: resetVoice, setFinalText } = useVoiceRecorder({
    onBlob: async (blob) => {
      const ext = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "mp4" : "webm";
      const form = new FormData();
      form.append("audio", blob, `recording.${ext}`);
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      const key = getStoredKey();
      if (key?.apiKey) headers["X-Api-Key"] = key.apiKey;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/profile/resume/transcribe`, {
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

  // ── Total time tracker ─────────────────────────────────────────────────────
  const startTotalTimer = useCallback(() => {
    totalStartRef.current = Date.now() - totalMs;
    totalTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - totalStartRef.current;
      setTotalMs(elapsed);
      if (elapsed >= MAX_TOTAL_MS) {
        void stop();
      }
    }, 500);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalMs]);

  const stopTotalTimer = useCallback(() => {
    if (totalTimerRef.current) { clearInterval(totalTimerRef.current); totalTimerRef.current = null; }
  }, []);

  useEffect(() => () => stopTotalTimer(), [stopTotalTimer]);

  // ── Auto-stop segment at 60s ───────────────────────────────────────────────
  const clearSegmentTimer = useCallback(() => {
    if (segmentTimerRef.current) { clearTimeout(segmentTimerRef.current); segmentTimerRef.current = null; }
  }, []);

  // ── Stop current segment and commit ───────────────────────────────────────
  const stopCurrentSegment = useCallback(async () => {
    clearSegmentTimer();
    stopTotalTimer();
    await stop();
  }, [stop, clearSegmentTimer, stopTotalTimer]);

  // ── Start recording a new segment ─────────────────────────────────────────
  const startNewSegment = useCallback(async () => {
    if (segments.length >= MAX_SEGMENTS) return;
    setError(null);
    resetVoice();
    setRecordingState("recording");
    startTotalTimer();
    await start();
    segmentTimerRef.current = setTimeout(() => { void stopCurrentSegment(); }, SEGMENT_DURATION_MS);
  }, [segments.length, start, resetVoice, startTotalTimer, stopCurrentSegment]);

  // When voiceState reaches "preview", commit the segment
  useEffect(() => {
    if (voiceState !== "preview") return;
    const text = finalText.trim();
    if (!text) return;

    if (recordingState === "re-recording" && reRecordingIndex !== null) {
      setSegments((prev) => prev.map((s, i) => i === reRecordingIndex ? text : s));
      setReRecordingIndex(null);
    } else {
      setSegments((prev) => [...prev, text]);
    }
    setRecordingState("idle");
    resetVoice();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceState]);

  // ── Re-record a specific segment ──────────────────────────────────────────
  const startReRecord = useCallback(async (index: number) => {
    resetVoice();
    setReRecordingIndex(index);
    setRecordingState("re-recording");
    setError(null);
    await start();
    segmentTimerRef.current = setTimeout(() => { void stopCurrentSegment(); }, SEGMENT_DURATION_MS);
  }, [resetVoice, start, stopCurrentSegment]);

  // ── Delete a segment ──────────────────────────────────────────────────────
  const deleteSegment = (index: number) => {
    setSegments((prev) => prev.filter((_, i) => i !== index));
  };

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (segments.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const key = getStoredKey();
      const result = await submitStory(segments, token, {
        byokApiKey: key?.apiKey,
        byokProvider: key?.provider,
        byokModel: key?.model,
        whisperPath: !supportsWebSpeech,
      });
      setReviewText(result.resume_text ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate resume from story.");
    } finally {
      setSubmitting(false);
    }
  };

  const handlePolish = async () => {
    if (!polishInstruction.trim() || !reviewText || polishing) return;
    setPolishing(true);
    setPolishError(null);
    setPrevText(reviewText);
    try {
      const key = getStoredKey();
      const result = await polishResume(reviewText, polishInstruction.trim(), token, {
        byokApiKey: key?.apiKey,
        byokProvider: key?.provider,
        byokModel: key?.model,
      });
      setReviewText(result.text);
      setPolishInstruction("");
    } catch (e) {
      setPolishError(e instanceof Error ? e.message : "Polish failed. Try again.");
      setPrevText(null);
    } finally {
      setPolishing(false);
      setTimeout(() => polishInputRef.current?.focus(), 50);
    }
  };

  const isRecordingAnything = recordingState !== "idle";
  const canAddSegment = segments.length < MAX_SEGMENTS && !isRecordingAnything && !submitting;
  const totalMinsLabel = `${Math.floor(totalMs / 60000)}:${String(Math.floor((totalMs % 60000) / 1000)).padStart(2, "0")}`;
  const isWarning = totalMs >= WARN_TOTAL_MS;

  // ── Submitting overlay ─────────────────────────────────────────────────────
  if (submitting) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
        <Loader2 className="w-10 h-10 text-amber-400 animate-spin" />
        <p className="text-slate-300 font-medium">Crafting your resume from the story…</p>
        <p className="text-slate-500 text-sm">This may take up to 30 seconds</p>
      </div>
    );
  }

  // ── Review state ───────────────────────────────────────────────────────────
  if (reviewText !== null) {
    return (
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            <p className="text-green-400 font-semibold text-sm">Resume crafted from your story</p>
          </div>
          {prevText && (
            <button
              type="button"
              onClick={() => { setReviewText(prevText); setPrevText(null); }}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-amber-400 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Undo last polish
            </button>
          )}
        </div>

        <p className="text-slate-400 text-sm">
          Review and edit below. Use the AI assistant to refine any section, then save to your profile.
        </p>

        {/* Editable resume textarea */}
        <textarea
          value={reviewText}
          onChange={(e) => { setReviewText(e.target.value); setPrevText(null); }}
          rows={18}
          className="w-full bg-slate-900 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm font-mono leading-relaxed resize-y focus:outline-none focus:border-amber-400/50"
        />

        {/* AI Polish panel */}
        <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Wand2 className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-slate-300">Polish with AI</span>
            <span className="text-xs text-slate-600 ml-auto">Free — no credits used</span>
          </div>

          {/* Example prompts */}
          <div className="flex flex-wrap gap-2">
            {[
              "Make the summary more senior",
              "Add stronger metrics to experience",
              "Make bullets more concise",
              "Improve the skills section",
            ].map((ex) => (
              <button
                key={ex}
                type="button"
                disabled={polishing}
                onClick={() => {
                  setPolishInstruction(ex);
                  setTimeout(() => polishInputRef.current?.focus(), 30);
                }}
                className="text-xs px-2.5 py-1 rounded-full border border-slate-700 text-slate-400 hover:border-amber-400/50 hover:text-amber-300 transition-colors disabled:opacity-40"
              >
                {ex}
              </button>
            ))}
          </div>

          {/* Instruction input */}
          <div className="flex gap-2">
            <textarea
              ref={polishInputRef}
              value={polishInstruction}
              onChange={(e) => setPolishInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handlePolish();
                }
              }}
              disabled={polishing}
              placeholder="Tell AI what to change… (Enter to send)"
              rows={2}
              className="flex-1 resize-none bg-slate-900 border border-slate-700 focus:border-amber-400/60 rounded-xl px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none transition-colors disabled:opacity-40 leading-relaxed"
            />
            <button
              type="button"
              onClick={() => void handlePolish()}
              disabled={polishing || !polishInstruction.trim()}
              className="px-3 py-2 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-900 disabled:opacity-40 transition-colors shrink-0 self-end"
            >
              {polishing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>

          {polishError && (
            <p className="text-red-400 text-xs bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
              {polishError}
            </p>
          )}

          {polishing && (
            <p className="text-slate-500 text-xs flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin" />
              Applying changes…
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            type="button"
            onClick={() => onSaved()}
            className="flex-1 py-3 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 text-sm"
          >
            <CheckCircle className="w-4 h-4" />
            Save to Profile &amp; continue
          </button>
          <button
            type="button"
            onClick={() => { setReviewText(null); setPrevText(null); }}
            className="px-5 py-3 border border-slate-700 hover:border-slate-500 bg-slate-800 text-slate-400 hover:text-white font-medium rounded-xl transition-colors text-sm"
          >
            Back
          </button>
        </div>
        <p className="text-slate-600 text-xs">
          Your resume is already saved — this view lets you refine it before continuing to the JD flow.
        </p>
      </div>
    );
  }

  // ── Credit disclosure (shown before first segment) ─────────────────────────
  if (segments.length === 0 && !isRecordingAnything) {
    return (
      <div className="space-y-6">
        <div className={cn(
          "rounded-xl border p-5 space-y-3",
          supportsWebSpeech ? "border-green-500/30 bg-green-500/5" : "border-amber-500/30 bg-amber-500/5",
        )}>
          <div className="flex items-center gap-2">
            <Mic className={cn("w-4 h-4", supportsWebSpeech ? "text-green-400" : "text-amber-400")} />
            <span className={cn("font-semibold text-sm", supportsWebSpeech ? "text-green-400" : "text-amber-400")}>
              {supportsWebSpeech ? "Live transcription — free, no API key needed" : "AI transcription via Whisper"}
            </span>
          </div>
          {supportsWebSpeech ? (
            <p className="text-slate-400 text-sm">
              Your browser supports live transcription. Words appear as you speak. Generating your resume from story: <strong className="text-white">0 credits</strong>.
            </p>
          ) : (
            <div className="space-y-2">
              <p className="text-slate-400 text-sm">
                Your browser does not support live transcription. We&apos;ll use Whisper AI to transcribe each segment.
                Cost: <strong className="text-white">2 credits per story</strong>.
              </p>
              <p className="text-slate-500 text-xs">
                Switch to Chrome or Edge to record for free.
              </p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-5 space-y-2">
          <p className="text-slate-300 font-medium text-sm">How it works</p>
          <ol className="text-slate-400 text-sm space-y-1 list-decimal list-inside">
            <li>Record up to 30 segments of 60 seconds each (30 min total)</li>
            <li>Talk naturally — jobs, skills, accomplishments, education</li>
            <li>Edit any segment after recording</li>
            <li>Click &ldquo;Generate resume from story&rdquo; when done</li>
          </ol>
          <p className="text-slate-500 text-xs pt-1">
            <Clock className="w-3 h-3 inline mr-1" />
            Most people finish in 10–15 minutes
          </p>
        </div>

        <button
          type="button"
          onClick={() => void startNewSegment()}
          className="w-full py-4 bg-red-500 hover:bg-red-400 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
        >
          <Mic className="w-5 h-5" />
          {supportsWebSpeech ? "Start your story — free" : "Start your story — 2 credits"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-3 px-1">
        <span className="text-slate-400 text-sm">
          <span className="text-white font-semibold">{segments.length}</span> / {MAX_SEGMENTS} segments
        </span>
        <span className={cn("text-sm tabular-nums font-mono", isWarning ? "text-amber-400" : "text-slate-400")}>
          {totalMinsLabel} / 30:00
          {isWarning && <span className="ml-2 text-amber-400 text-xs">⚠ Almost at limit</span>}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", isWarning ? "bg-amber-400" : "bg-amber-400/60")}
          style={{ width: `${Math.min((totalMs / MAX_TOTAL_MS) * 100, 100)}%` }}
        />
      </div>

      {/* Segment list */}
      <div className="space-y-3">
        {segments.map((text, i) => (
          <StorySegment
            key={i}
            index={i}
            text={text}
            isRecording={recordingState === "re-recording" && reRecordingIndex === i}
            disabled={isRecordingAnything || submitting}
            onChange={(newText) => setSegments((prev) => prev.map((s, j) => j === i ? newText : s))}
            onReRecord={() => void startReRecord(i)}
            onDelete={() => deleteSegment(i)}
          />
        ))}
      </div>

      {/* Current recording indicator (new segment) */}
      {recordingState === "recording" && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
            </span>
            <span className="text-red-400 text-sm font-medium">
              Recording segment {segments.length + 1} · {durationLabel}
            </span>
            <button
              type="button"
              onClick={() => void stopCurrentSegment()}
              className="ml-auto px-3 py-1 bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold rounded-full transition-colors"
            >
              Done
            </button>
          </div>
          {/* Live transcript */}
          <div className="min-h-12 text-sm leading-relaxed pl-1">
            <span className="text-slate-200">{finalText}</span>
            {finalText && interimText && " "}
            {interimText && <span className="text-slate-500 italic">{interimText}</span>}
            {!finalText && !interimText && (
              <span className="text-slate-600 italic">Start speaking…</span>
            )}
          </div>
        </div>
      )}

      {/* Whisper transcribing */}
      {voiceState === "transcribing" && (
        <div className="flex items-center gap-2 text-slate-400 text-sm py-3 justify-center">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          Transcribing segment with Whisper…
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-3 pt-2">
        {canAddSegment && (
          <button
            type="button"
            onClick={() => void startNewSegment()}
            className="flex-1 py-3 border border-slate-700 hover:border-amber-400/50 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-2 text-sm"
          >
            <Mic className="w-4 h-4" />
            {segments.length === 0 ? "Start recording" : "Record next segment"}
          </button>
        )}

        {segments.length > 0 && !isRecordingAnything && (
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting}
            className="flex-1 py-3 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 disabled:opacity-50 text-sm"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
                Generating resume…
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Generate resume from story
              </>
            )}
          </button>
        )}
      </div>

      {error && (
        <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          {error}
        </div>
      )}
    </div>
  );
}
