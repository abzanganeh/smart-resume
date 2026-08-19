"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MessageSquare, Send, SkipForward, Sparkles, X } from "lucide-react";
import {
  chatWithResume,
  type BlockingIssue,
  type ChatMessage,
  type ChatResponse,
  type ResumePatch,
  type TailoredResumeOutput,
} from "@/lib/api";
import { countPlaceablePatches } from "@/lib/suggestionHighlight";
import { normalizeResumePatch } from "@/lib/applyResumePatch";

// ── Message types ─────────────────────────────────────────────────────────────

interface AssistantMessage {
  role: "assistant";
  content: string;
  suggestionCount: number;
  unplaceableCount: number;
}
interface UserMessageEntry {
  role: "user";
  content: string;
}
type MessageEntry = UserMessageEntry | AssistantMessage;

// ── Chat bubbles ──────────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] bg-amber-400 text-slate-900 rounded-2xl rounded-tr-sm px-3 py-2 text-sm font-medium leading-relaxed break-words whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({ message }: { message: AssistantMessage }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-2">
        <div className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center shrink-0 mt-0.5">
          <MessageSquare className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400" />
        </div>
        <div className="flex-1 min-w-0 text-slate-700 dark:text-slate-300 text-sm leading-relaxed bg-slate-100/50 dark:bg-slate-800/50 rounded-2xl rounded-tl-sm px-3 py-2 space-y-2 break-words whitespace-pre-wrap">
          <p className="break-words whitespace-pre-wrap">{message.content}</p>
          {message.suggestionCount > 0 && (
            <div className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400/80 border-t border-slate-300 dark:border-slate-700/50 pt-2">
              <Sparkles className="w-3 h-3" />
              {message.suggestionCount} yellow highlight{message.suggestionCount !== 1 ? "s" : ""} in resume — click Accept to apply (not applied yet)
            </div>
          )}
          {message.unplaceableCount > 0 && (
            <div className="text-[11px] text-red-700 dark:text-red-300/90 border-t border-slate-300 dark:border-slate-700/50 pt-2 space-y-1">
              <p>
                {message.unplaceableCount} suggestion{message.unplaceableCount !== 1 ? "s" : ""} could not be matched to your resume
                {message.suggestionCount === 0 ? " — nothing was highlighted" : ""}.
              </p>
              <p className="text-slate-600 dark:text-slate-400">
                Check the <strong className="text-slate-700 dark:text-slate-300">Couldn&apos;t apply</strong> banner above the resume, or edit manually (trash icon / pencil).
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-2">
      <div className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center shrink-0">
        <MessageSquare className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400" />
      </div>
      <div className="bg-slate-100/50 dark:bg-slate-800/50 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

// ── Queue banner ──────────────────────────────────────────────────────────────

interface QueueBanner {
  issue: BlockingIssue;
  current: number;
  total: number;
  onSkip: () => void;
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  sessionId: string;
  tailored: TailoredResumeOutput | null;
  /** Called with every batch of patches returned by the AI — parent turns them into inline suggestions. */
  onSuggestPatches: (patches: ResumePatch[]) => void;
  prefillMessage?: string | null;
  onClearPrefill?: () => void;
  queueBanner?: QueueBanner | null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ResumeChat({ sessionId, tailored, onSuggestPatches, prefillMessage, onClearPrefill, queueBanner }: Props) {
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, loading]);

  useEffect(() => {
    if (!prefillMessage) return;
    setInput(prefillMessage);
    onClearPrefill?.();
    setTimeout(() => {
      inputRef.current?.focus();
      const len = prefillMessage.length;
      inputRef.current?.setSelectionRange(len, len);
    }, 50);
  }, [prefillMessage, onClearPrefill]);

  function buildHistory(): ChatMessage[] {
    return messages.map((m) => ({ role: m.role, content: m.content }));
  }

  async function send() {
    const text = input.trim();
    if (!text || loading || !tailored) return;

    const resume = tailored;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const res: ChatResponse = await chatWithResume(sessionId, {
        message: text,
        history: buildHistory(),
        tailored_snapshot: resume,
      });

      if (res.patches.length > 0) {
        onSuggestPatches(res.patches);
      }

      const normalized = res.patches.map((p) => normalizeResumePatch(resume, p));
      const { placeable, unplaceable } = countPlaceablePatches(normalized, resume);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.reply,
          suggestionCount: placeable,
          unplaceableCount: unplaceable,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong. Please try again.",
          suggestionCount: 0,
          unplaceableCount: 0,
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }

  const noResume = !tailored;

  return (
    <div className="flex flex-col h-full min-h-0">
      {queueBanner && (
        <div className="shrink-0 border-b border-amber-400/20 bg-amber-500/5 dark:bg-amber-400/5 px-3 py-2.5 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-amber-700 dark:text-amber-400 font-semibold uppercase tracking-wider">
              Issue {queueBanner.current} / {queueBanner.total}
            </span>
            <button
              type="button"
              onClick={queueBanner.onSkip}
              className="flex items-center gap-1 text-[10px] text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 transition-colors"
            >
              <SkipForward className="w-3 h-3" />
              Skip
            </button>
          </div>
          <p className="text-slate-800 dark:text-slate-200 text-xs font-medium leading-snug">
            {queueBanner.issue.description}
          </p>
          <p className="text-slate-600 dark:text-slate-400 text-[11px] leading-snug">
            {queueBanner.issue.suggestion}
          </p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[6.5rem]">
        {messages.length === 0 && (
          <div className="text-center py-8 space-y-3">
            <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mx-auto">
              <MessageSquare className="w-5 h-5 text-amber-700 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-slate-700 dark:text-slate-300 text-sm font-medium">Resume Chat</p>
              <p className="text-slate-600 dark:text-slate-400 text-xs mt-1 leading-relaxed">
                Ask me to improve anything — suggestions appear inline in the resume on the left.
              </p>
            </div>
            <div className="space-y-1.5 text-left">
              {[
                "What's missing to increase my ATS score?",
                "Rewrite my summary for this role",
                "Add Snowflake to my skills",
                "Make my IBM bullets more technical",
              ].map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => { setInput(ex); inputRef.current?.focus(); }}
                  className="w-full text-left text-xs text-slate-600 dark:text-slate-400 hover:text-amber-800 dark:hover:text-amber-400 bg-slate-100/50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-300 dark:border-slate-700/50 rounded-lg px-3 py-2 transition-colors"
                >
                  &ldquo;{ex}&rdquo;
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) =>
          msg.role === "user" ? (
            <UserBubble key={idx} content={msg.content} />
          ) : (
            <AssistantBubble key={idx} message={msg} />
          ),
        )}

        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-300 dark:border-slate-700/60 p-3 space-y-2">
        {noResume && (
          <p className="text-xs text-amber-700 dark:text-amber-400/80 bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/20 rounded-lg px-2 py-1.5">
            Run the Tailored Rewrite first to enable chat editing.
          </p>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
              if (e.key === "Escape") {
                setInput("");
              }
            }}
            disabled={loading || noResume}
            placeholder={noResume ? "Run rewrite first…" : "Ask me to change anything… (Enter to send)"}
            rows={4}
            className="flex-1 resize-none bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 focus:border-amber-400/60 rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-600 outline-none transition-colors disabled:opacity-40 leading-relaxed min-h-[6.5rem]"
          />
          <div className="flex flex-col gap-2">
            {input.trim() && !loading && (
              <button
                type="button"
                onClick={() => setInput("")}
                title="Clear message (Esc)"
                className="p-2.5 rounded-xl bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 transition-colors shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <button
              type="button"
              onClick={() => void send()}
              disabled={loading || !input.trim() || noResume}
              className="p-2.5 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-900 disabled:opacity-40 transition-colors shrink-0"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
        <p className="text-[10px] text-slate-600 dark:text-slate-400">Shift+Enter for new line · Enter to send · Esc to clear</p>
      </div>
    </div>
  );
}
