"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceState = "idle" | "speaking" | "recording" | "transcribing" | "preview";

/**
 * Unified voice-recording hook.
 *
 * Primary path  — Web Speech API (Chrome / Edge):
 *   No API key required. Live interim text appears as the user speaks.
 *   Transcript is ready the moment the user stops; no backend call needed.
 *
 * Fallback path — MediaRecorder → OpenAI Whisper:
 *   Used when SpeechRecognition is not available (Firefox, Safari).
 *   Requires an OpenAI API key (BYOK or backend .env).
 */

function formatDuration(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

interface UseVoiceRecorderOptions {
  /** Called with a final blob only on the MediaRecorder fallback path. */
  onBlob?: (blob: Blob) => Promise<void>;
}

export function useVoiceRecorder({ onBlob }: UseVoiceRecorderOptions = {}) {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [finalText, setFinalText]   = useState("");
  const [interimText, setInterimText] = useState("");
  const [recordingMs, setRecordingMs] = useState(0);
  const [error, setError]           = useState<string | null>(null);

  const recognitionRef  = useRef<SpeechRecognition | null>(null);
  const mediaRecRef     = useRef<MediaRecorder | null>(null);
  const chunksRef       = useRef<Blob[]>([]);
  const timerRef        = useRef<ReturnType<typeof setInterval> | null>(null);
  const startMsRef      = useRef(0);

  const supportsWebSpeech =
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition ?? window.webkitSpeechRecognition);

  // Cleanup on unmount
  useEffect(() => () => {
    recognitionRef.current?.stop();
    mediaRecRef.current?.stream?.getTracks().forEach((t) => t.stop());
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const startTimer = () => {
    startMsRef.current = Date.now();
    setRecordingMs(0);
    timerRef.current = setInterval(
      () => setRecordingMs(Date.now() - startMsRef.current),
      500,
    );
  };

  const stopTimer = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };

  // ── Web Speech API path ────────────────────────────────────────────────────
  const startWebSpeech = useCallback(() => {
    const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Ctor) return false;

    const rec = new Ctor();
    rec.continuous      = true;
    rec.interimResults  = true;
    rec.lang            = "en-US";
    recognitionRef.current = rec;

    let accumulated = "";

    rec.onresult = (e: SpeechRecognitionEvent) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const text = e.results[i][0].transcript;
        if (e.results[i].isFinal) {
          accumulated += (accumulated ? " " : "") + text.trim();
        } else {
          interim = text;
        }
      }
      setFinalText(accumulated);
      setInterimText(interim);
    };

    rec.onerror = (e: SpeechRecognitionErrorEvent) => {
      if (e.error === "aborted") return; // intentional stop
      setError(`Speech recognition error: ${e.error}`);
      setVoiceState("idle");
      stopTimer();
    };

    rec.onend = () => {
      stopTimer();
      setInterimText("");
      setVoiceState((s) => (s === "speaking" ? "preview" : s));
    };

    rec.start();
    startTimer();
    setVoiceState("speaking");
    setFinalText("");
    setInterimText("");
    setError(null);
    return true;
  }, []);

  // ── MediaRecorder fallback ─────────────────────────────────────────────────
  const startMediaRecorder = useCallback(async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access denied. Allow microphone permission and try again.");
      return;
    }
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";

    chunksRef.current = [];
    const mr = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    mr.onstop = () => stream.getTracks().forEach((t) => t.stop());
    mr.start(250);
    mediaRecRef.current = mr;
    startTimer();
    setVoiceState("recording");
    setFinalText("");
    setError(null);
  }, []);

  // ── Start (picks the best path) ────────────────────────────────────────────
  const start = useCallback(async () => {
    if (supportsWebSpeech) {
      startWebSpeech();
    } else {
      await startMediaRecorder();
    }
  }, [supportsWebSpeech, startWebSpeech, startMediaRecorder]);

  // ── Stop ───────────────────────────────────────────────────────────────────
  const stop = useCallback(async () => {
    stopTimer();

    // Web Speech path
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      // onend will set voiceState → "preview"
      return;
    }

    // MediaRecorder fallback path
    const mr = mediaRecRef.current;
    if (!mr) return;
    await new Promise<void>((resolve) => {
      mr.addEventListener("stop", () => resolve(), { once: true });
      mr.stop();
    });
    mediaRecRef.current = null;

    if (!onBlob) {
      setVoiceState("preview");
      return;
    }
    setVoiceState("transcribing");
    try {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
      await onBlob(blob);
      setVoiceState("preview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Transcription failed.");
      setVoiceState("idle");
    }
  }, [onBlob]);

  const reset = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    mediaRecRef.current?.stream?.getTracks().forEach((t) => t.stop());
    mediaRecRef.current = null;
    stopTimer();
    setVoiceState("idle");
    setFinalText("");
    setInterimText("");
    setError(null);
    setRecordingMs(0);
  }, []);

  return {
    voiceState,
    finalText,
    setFinalText,
    interimText,
    recordingMs,
    durationLabel: formatDuration(recordingMs),
    error,
    setError,
    supportsWebSpeech,
    start,
    stop,
    reset,
  };
}
