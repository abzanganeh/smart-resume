"use client";

/**
 * StoryCoach — interview coach panel that appears below a recorded segment.
 *
 * Behaviour:
 *  - On mount: immediately fires the first coaching question (no user action).
 *  - User can reply by typing or using the 30-s mic button.
 *  - After MAX_EXCHANGES (3) coach questions the input is locked.
 *  - [Add as segment] appends all user answers as a new segment text.
 *  - [Close] dismisses the panel without adding anything.
 *  - Free users: 1 credit per story build session (backend handles dedup via session_id).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, Loader2, Mic, MicOff, Send, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { ExhaustionPaywall } from "@/components/billing/ExhaustionPaywall";
import { type CoachMessage, streamCoach } from "@/lib/story";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";

const MAX_EXCHANGES = 3;
const COACH_MIC_DURATION_MS = 30_000;

interface Props {
  segmentText: string;
  token: string;
  storyBuildSessionId: string;
  coachSessionUnlocked: boolean;
  onCoachSessionUnlocked: () => void;
  isFreeUser: boolean;
  onAddAsSegment: (text: string) => void;
  onClose: () => void;
}

export function StoryCoach({
  segmentText,
  token,
  storyBuildSessionId,
  coachSessionUnlocked,
  onCoachSessionUnlocked,
  isFreeUser,
  onAddAsSegment,
  onClose,
}: Props) {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showExhaustionPaywall, setShowExhaustionPaywall] = useState(false);
  const [isSegmentComplete, setIsSegmentComplete] = useState(false);
  const [creditAccepted, setCreditAccepted] = useState(
    !isFreeUser || coachSessionUnlocked,
  );

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const coachTurns = messages.filter((m) => m.role === "coach").length;
  const atLimit = coachTurns >= MAX_EXCHANGES;
  const userAnswers = messages.filter((m) => m.role === "user").map((m) => m.text);
  const exchangesLeft = Math.max(0, MAX_EXCHANGES - coachTurns);

  useEffect(() => {
    if (coachSessionUnlocked) {
      setCreditAccepted(true);
    }
  }, [coachSessionUnlocked]);

  // Voice recorder for 30-s micro answers (Web Speech or Whisper fallback)
  const {
    voiceState,
    finalText: micFinalText,
    start: startRecording,
    stop: stopRecording,
    reset: resetMic,
  } = useVoiceRecorder();
  const isRecording = voiceState === "speaking" || voiceState === "recording";

  // When the mic produces a final transcript, append it to the input field
  useEffect(() => {
    if (micFinalText) {
      setInput((prev) => (prev ? `${prev} ${micFinalText}` : micFinalText));
      resetMic();
    }
  }, [micFinalText, resetMic]);

  const scrollBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const fireCoachQuestion = useCallback(
    async (history: CoachMessage[]) => {
      setStreamingText("");
      setIsStreaming(true);
      setError(null);

      let accumulated = "";
      try {
        const result = await streamCoach(
          segmentText,
          history,
          token,
          (delta) => {
            accumulated += delta;
            setStreamingText(accumulated);
            scrollBottom();
          },
          {
            sessionId: storyBuildSessionId,
          },
        );

        if (history.length === 0 && isFreeUser && !coachSessionUnlocked) {
          onCoachSessionUnlocked();
        }

        // Commit streamed text as a coach message
        const coachText = accumulated.trim();
        setMessages((prev) => [...prev, { role: "coach", text: coachText }]);
        setStreamingText("");

        if (result.complete) {
          setIsSegmentComplete(true);
        }
      } catch (err: unknown) {
        const e = err as Error & { code?: string };
        if (e.code === "insufficient_credits") {
          setError("You need at least 1 credit to start a coaching session.");
          setShowExhaustionPaywall(true);
        } else {
          setError(e.message ?? "Coach request failed. Please try again.");
          setShowExhaustionPaywall(false);
        }
      } finally {
        setIsStreaming(false);
        scrollBottom();
        inputRef.current?.focus();
      }
    },
    [segmentText, token, scrollBottom, storyBuildSessionId, isFreeUser, coachSessionUnlocked, onCoachSessionUnlocked],
  );

  // Fire first question on mount (once credit accepted)
  useEffect(() => {
    if (creditAccepted && messages.length === 0 && !isStreaming) {
      fireCoachQuestion([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [creditAccepted]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming || atLimit) return;

    const userMsg: CoachMessage = { role: "user", text };
    const nextHistory = [...messages, userMsg];
    setMessages(nextHistory);
    setInput("");

    if (nextHistory.filter((m) => m.role === "coach").length < MAX_EXCHANGES) {
      await fireCoachQuestion(nextHistory);
    }
  }, [input, isStreaming, atLimit, messages, fireCoachQuestion]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleAddAsSegment = useCallback(() => {
    const combined = userAnswers.join(" ").trim();
    if (combined) onAddAsSegment(combined);
    else onClose();
  }, [userAnswers, onAddAsSegment, onClose]);

  // Credit disclosure for free users
  if (!creditAccepted) {
    return (
      <div className="rounded-xl border border-indigo-500/30 bg-indigo-50 dark:bg-indigo-950/20 p-4 space-y-3 text-sm">
        <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300 font-semibold">
          <Sparkles className="w-4 h-4" />
          Interview Coach
        </div>
        <p className="text-slate-700 dark:text-slate-300">
          The coach asks follow-up questions (up to {MAX_EXCHANGES} per segment) to help you add
          missing metrics and outcomes.{" "}
          <span className="text-amber-700 dark:text-amber-400 font-medium">1 credit</span> unlocks coaching for this
          entire resume build — all segments included.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setCreditAccepted(true)}
            className="flex-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-2 text-sm font-medium transition-colors"
          >
            Use 1 credit
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 dark:border-slate-700 hover:border-slate-500 text-slate-600 dark:text-slate-400 px-3 py-2 text-sm transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-indigo-500/30 bg-indigo-50 dark:bg-indigo-950/20 p-4 space-y-3 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300 font-semibold">
          <Sparkles className="w-4 h-4" />
          Interview Coach
          {coachTurns > 0 && (
            <span className="ml-1 text-xs text-slate-600 dark:text-slate-400 font-normal">
              {exchangesLeft > 0
                ? `${exchangesLeft} question${exchangesLeft === 1 ? "" : "s"} left on this segment`
                : "No questions left on this segment"}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close coach panel"
          className="text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Message thread */}
      <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "rounded-lg px-3 py-2 text-sm leading-relaxed",
              msg.role === "coach"
                ? "bg-slate-100/60 dark:bg-slate-800/60 text-slate-800 dark:text-slate-200"
                : "bg-indigo-50 dark:bg-indigo-900/40 text-indigo-900 dark:text-indigo-100 ml-4",
            )}
          >
            {msg.text}
          </div>
        ))}

        {/* Live streaming text */}
        {isStreaming && (
          <div className="rounded-lg px-3 py-2 bg-slate-100/60 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300 text-sm leading-relaxed">
            {streamingText}
            <span className="inline-block w-1 h-4 ml-0.5 bg-indigo-400 animate-pulse align-middle" />
          </div>
        )}

        {/* Loading spinner on very first fetch before any text arrives */}
        {isStreaming && !streamingText && (
          <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 text-xs">
            <Loader2 className="w-3 h-3 animate-spin" />
            Thinking…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && (
        <p className="text-red-700 dark:text-red-400 text-xs rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-500/20 px-3 py-2">
          {error}
        </p>
      )}

      {showExhaustionPaywall && (
        <ExhaustionPaywall
          token={token}
          compact
          contextMessage="You need credits to use Interview Coach"
          onCreditsRefreshed={() => {
            setShowExhaustionPaywall(false);
            setError(null);
          }}
        />
      )}

      {/* Segment complete notice */}
      {isSegmentComplete && !error && (
        <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400 text-xs bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-500/20 rounded-lg px-3 py-2">
          <CheckCircle className="w-3.5 h-3.5 shrink-0" />
          This segment already has strong detail — nothing missing!
        </div>
      )}

      {/* At-limit notice */}
      {atLimit && !isSegmentComplete && (
        <p className="text-slate-600 dark:text-slate-400 text-xs text-center">
          Maximum {MAX_EXCHANGES} exchanges reached for this segment.
        </p>
      )}

      {/* Input area */}
      {!atLimit && !isSegmentComplete && (
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            placeholder="Type your answer… (Enter to send)"
            className={cn(
              "flex-1 resize-none rounded-lg border bg-white/60 dark:bg-slate-900/60 px-3 py-2 text-sm",
              "text-slate-800 dark:text-slate-200 placeholder:text-slate-500 dark:placeholder:text-slate-600",
              "border-slate-300 dark:border-slate-700 focus:border-indigo-500 focus:outline-none transition-colors",
              "disabled:opacity-50",
            )}
          />
          {/* Mic button */}
          <button
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isStreaming}
            aria-label={isRecording ? "Stop recording" : "Record answer"}
            className={cn(
              "rounded-lg p-2 transition-colors disabled:opacity-40",
              isRecording
                ? "bg-red-600 hover:bg-red-500 text-white"
                : "border border-slate-300 dark:border-slate-700 hover:border-slate-500 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200",
            )}
          >
            {isRecording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>
          {/* Send button */}
          <button
            type="button"
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            aria-label="Send answer"
            className="rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white p-2 transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Add as segment / dismiss */}
      {(atLimit || isSegmentComplete) && (
        <div className="flex gap-2 pt-1">
          {userAnswers.length > 0 && (
            <button
              type="button"
              onClick={handleAddAsSegment}
              className="flex-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-2 text-sm font-medium transition-colors"
            >
              Add answers as segment
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg border border-slate-300 dark:border-slate-700 hover:border-slate-500 text-slate-600 dark:text-slate-400 px-3 py-2 text-sm transition-colors"
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
