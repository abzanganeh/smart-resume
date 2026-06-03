"use client";

/**
 * StoryInterview — Coached Interview Mode for Story Mode (§23).
 *
 * Behaviour:
 *  - On mount: fires the first AI interview question immediately.
 *  - User answers by typing or speaking (Web Speech / Whisper).
 *  - After each answer, the AI streams the next question.
 *  - When the AI emits INTERVIEW_COMPLETE (or user clicks "Done"), shows
 *    a "Generate resume" button that calls POST /story/interview/submit.
 *  - Free users: 1 credit charged on first question (backend handles this).
 *  - Supports "Go back" to return to the mode selector.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  Send,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { type InterviewMessage, streamInterviewQuestion, submitInterview } from "@/lib/story";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { getStoredKey } from "@/lib/keyStore";

const MAX_QUESTIONS = 15;

interface Props {
  token: string;
  isFreeUser: boolean;
  onSaved: () => void;
  onBack: () => void;
}

type InterviewPhase = "credit-disclosure" | "interviewing" | "complete" | "generating" | "done";

export function StoryInterview({ token, isFreeUser, onSaved, onBack }: Props) {
  const [phase, setPhase] = useState<InterviewPhase>(
    isFreeUser ? "credit-disclosure" : "interviewing",
  );
  const [history, setHistory] = useState<InterviewMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [reviewText, setReviewText] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const storedKey = getStoredKey();
  const byokApiKey  = storedKey?.apiKey;
  const byokProvider = storedKey?.provider;
  const byokModel    = storedKey?.model;

  const questionCount = history.filter((m) => m.role === "interviewer").length;
  const atLimit = questionCount >= MAX_QUESTIONS;

  // Voice recorder
  const { voiceState, finalText: micFinalText, start: startMic, stop: stopMic, reset: resetMic } =
    useVoiceRecorder();
  const isRecording = voiceState === "speaking" || voiceState === "recording";

  useEffect(() => {
    if (micFinalText) {
      setInput((prev) => (prev ? `${prev} ${micFinalText}` : micFinalText));
      resetMic();
    }
  }, [micFinalText, resetMic]);

  const scrollBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const fireNextQuestion = useCallback(
    async (currentHistory: InterviewMessage[]) => {
      setStreamingText("");
      setIsStreaming(true);
      setError(null);

      let accumulated = "";
      try {
        const result = await streamInterviewQuestion(
          currentHistory,
          token,
          (delta) => {
            accumulated += delta;
            setStreamingText(accumulated);
            scrollBottom();
          },
          { byokApiKey, byokProvider, byokModel },
        );

        const questionText = accumulated.trim();
        const nextHistory: InterviewMessage[] = [
          ...currentHistory,
          { role: "interviewer", text: questionText },
        ];
        setHistory(nextHistory);
        setStreamingText("");

        if (result.complete || atLimit) {
          setPhase("complete");
        }
      } catch (err: unknown) {
        const e = err as Error & { code?: string };
        if (e.code === "insufficient_credits") {
          setError("You need at least 1 credit to start a coached interview. Upgrade to continue.");
          setPhase("credit-disclosure");
        } else {
          setError(e.message ?? "Failed to get next question. Please try again.");
        }
      } finally {
        setIsStreaming(false);
        scrollBottom();
        inputRef.current?.focus();
      }
    },
    [token, byokApiKey, byokProvider, byokModel, atLimit, scrollBottom],
  );

  // Start the interview on mount (or after credit accepted)
  useEffect(() => {
    if (phase === "interviewing" && history.length === 0 && !isStreaming) {
      fireNextQuestion([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming || phase !== "interviewing") return;

    const userMsg: InterviewMessage = { role: "user", text };
    const nextHistory = [...history, userMsg];
    setHistory(nextHistory);
    setInput("");

    if (nextHistory.filter((m) => m.role === "interviewer").length < MAX_QUESTIONS) {
      await fireNextQuestion(nextHistory);
    } else {
      setPhase("complete");
    }
  }, [input, isStreaming, phase, history, fireNextQuestion]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleGenerate = useCallback(async () => {
    setPhase("generating");
    setError(null);
    try {
      const result = await submitInterview(history, token, {
        byokApiKey,
        byokProvider,
        byokModel,
      });
      setReviewText(result.resume_text ?? null);
      setPhase("done");
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message ?? "Resume generation failed. Please try again.");
      setPhase("complete");
    }
  }, [history, token, byokApiKey, byokProvider, byokModel]);

  // ── Phases ─────────────────────────────────────────────────────────────────

  if (phase === "credit-disclosure") {
    return (
      <div className="rounded-2xl border border-amber-500/30 bg-amber-950/10 p-6 space-y-4 text-sm">
        <div className="flex items-center gap-2 text-amber-300 font-semibold text-base">
          <MessageSquare className="w-5 h-5" />
          Coached Interview
        </div>
        <p className="text-slate-300 leading-relaxed">
          The AI will ask you up to {MAX_QUESTIONS} structured career questions and follow up when
          answers lack specific metrics. Your answers are compiled into a resume at the end.
        </p>
        <p className="text-slate-300">
          This session costs{" "}
          <span className="text-amber-400 font-semibold">1 credit</span>. Subscribers and BYOK
          users pay nothing.
        </p>
        {error && (
          <p className="text-red-400 text-xs bg-red-950/20 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => { setError(null); setPhase("interviewing"); }}
            className="flex-1 rounded-xl bg-amber-600 hover:bg-amber-500 text-white px-4 py-2.5 font-medium transition-colors"
          >
            Use 1 credit · Start interview
          </button>
          <button
            type="button"
            onClick={onBack}
            className="rounded-xl border border-slate-700 hover:border-slate-500 text-slate-400 px-4 py-2.5 transition-colors"
          >
            Back
          </button>
        </div>
      </div>
    );
  }

  if (phase === "done" && reviewText) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-emerald-400 font-semibold">
          <CheckCircle className="w-5 h-5" />
          Resume generated from your interview
        </div>
        <textarea
          value={reviewText}
          onChange={(e) => setReviewText(e.target.value)}
          rows={14}
          className="w-full bg-slate-900 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-emerald-400"
        />
        <button
          type="button"
          onClick={onSaved}
          className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-3 font-semibold transition-colors"
        >
          Save to master resume →
        </button>
      </div>
    );
  }

  // ── Main interview UI ───────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-slate-300 font-semibold">
          <MessageSquare className="w-4 h-4 text-indigo-400" />
          Coached Interview
          {questionCount > 0 && (
            <span className="text-xs text-slate-500 font-normal ml-1">
              Question {questionCount} of up to {MAX_QUESTIONS}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onBack}
          disabled={isStreaming || phase === "generating"}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 disabled:opacity-40 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Change mode
        </button>
      </div>

      {/* Progress bar */}
      {questionCount > 0 && (
        <div className="h-1 rounded-full bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-indigo-500 transition-all"
            style={{ width: `${Math.min((questionCount / MAX_QUESTIONS) * 100, 100)}%` }}
          />
        </div>
      )}

      {/* Conversation thread */}
      <div className="space-y-3 max-h-80 overflow-y-auto pr-1 scroll-smooth">
        {history.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "rounded-xl px-4 py-3 text-sm leading-relaxed",
              msg.role === "interviewer"
                ? "bg-slate-800/70 text-slate-100 border border-slate-700/50"
                : "bg-indigo-900/30 text-indigo-100 ml-6 border border-indigo-800/30",
            )}
          >
            {msg.role === "interviewer" && (
              <p className="text-xs text-indigo-400 font-medium mb-1 flex items-center gap-1">
                <Sparkles className="w-3 h-3" /> Interviewer
              </p>
            )}
            {msg.text}
          </div>
        ))}

        {/* Live streaming question */}
        {isStreaming && (
          <div className="rounded-xl px-4 py-3 bg-slate-800/70 border border-slate-700/50 text-sm text-slate-200 leading-relaxed">
            <p className="text-xs text-indigo-400 font-medium mb-1 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Interviewer
            </p>
            {streamingText}
            <span className="inline-block w-1 h-4 ml-0.5 bg-indigo-400 animate-pulse align-middle" />
          </div>
        )}

        {/* Initial loading */}
        {isStreaming && !streamingText && history.length === 0 && (
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            Preparing your first question…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && (
        <p className="text-red-400 text-xs rounded-xl bg-red-950/20 border border-red-500/20 px-3 py-2">
          {error}
        </p>
      )}

      {/* Complete state */}
      {phase === "complete" && !isStreaming && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium bg-emerald-950/20 border border-emerald-500/20 rounded-xl px-4 py-3">
            <CheckCircle className="w-4 h-4 shrink-0" />
            All questions answered — ready to generate your resume!
          </div>
          <button
            type="button"
            onClick={handleGenerate}
            className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white px-4 py-3 font-semibold flex items-center justify-center gap-2 transition-all"
          >
            <Sparkles className="w-4 h-4" />
            Generate resume from interview
          </button>
          <button
            type="button"
            onClick={() => setPhase("interviewing")}
            className="w-full text-xs text-slate-500 hover:text-slate-300 transition-colors py-1"
          >
            Continue answering (add more detail)
          </button>
        </div>
      )}

      {/* Generating state */}
      {phase === "generating" && (
        <div className="flex items-center justify-center gap-3 py-6 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          Generating your resume from {history.filter((m) => m.role === "user").length} answers…
        </div>
      )}

      {/* Input area — shown during interview */}
      {phase === "interviewing" && !atLimit && (
        <div className="space-y-2">
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
              placeholder="Type your answer… (Enter to send, Shift+Enter for new line)"
              className={cn(
                "flex-1 resize-none rounded-xl border bg-slate-900/60 px-4 py-3 text-sm",
                "text-slate-200 placeholder:text-slate-600",
                "border-slate-700 focus:border-indigo-500 focus:outline-none transition-colors",
                "disabled:opacity-50",
              )}
            />
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={isRecording ? stopMic : startMic}
                disabled={isStreaming}
                aria-label={isRecording ? "Stop recording" : "Record answer"}
                className={cn(
                  "rounded-xl p-2.5 transition-colors disabled:opacity-40",
                  isRecording
                    ? "bg-red-600 hover:bg-red-500 text-white"
                    : "border border-slate-700 hover:border-slate-500 text-slate-400 hover:text-slate-200",
                )}
              >
                {isRecording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
              <button
                type="button"
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                aria-label="Send answer"
                className="rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white p-2.5 transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Done early button */}
          <button
            type="button"
            onClick={() => setPhase("complete")}
            disabled={history.filter((m) => m.role === "user").length < 2 || isStreaming}
            className="w-full text-xs text-slate-500 hover:text-slate-300 disabled:opacity-30 transition-colors py-1"
          >
            I'm done answering — generate resume now
          </button>
        </div>
      )}
    </div>
  );
}
