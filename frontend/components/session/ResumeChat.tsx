"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronRight, Loader2, MessageSquare, Send, X } from "lucide-react";
import {
  chatWithResume,
  type ChatMessage,
  type ChatResponse,
  type ResumePatch,
  type TailoredResumeOutput,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Patch state ──────────────────────────────────────────────────────────────

type PatchStatus = "pending" | "accepted" | "rejected";

interface AssistantMessage {
  role: "assistant";
  content: string;
  patches: ResumePatch[];
  patchStatuses: PatchStatus[];
}
interface UserMessageEntry {
  role: "user";
  content: string;
}
type MessageEntry = UserMessageEntry | AssistantMessage;

// ── Patch diff card ──────────────────────────────────────────────────────────

function PatchCard({
  patch,
  status,
  onAccept,
  onReject,
}: {
  patch: ResumePatch;
  status: PatchStatus;
  onAccept: () => void;
  onReject: () => void;
}) {
  const isAccepted = status === "accepted";
  const isRejected = status === "rejected";

  return (
    <div
      className={cn(
        "rounded-xl border p-3 text-xs space-y-2 transition-colors",
        isAccepted
          ? "bg-emerald-400/10 border-emerald-400/30"
          : isRejected
          ? "bg-slate-800/30 border-slate-700/30 opacity-50"
          : "bg-slate-800/60 border-slate-700/50",
      )}
    >
      {/* Section badge */}
      <div className="flex items-center gap-1.5">
        <span className="uppercase tracking-wider text-[10px] font-bold text-amber-400/80">
          {patch.section}
        </span>
        {isAccepted && <Check className="w-3 h-3 text-emerald-400" />}
        {isRejected && <X className="w-3 h-3 text-slate-500" />}
      </div>

      {/* Description */}
      <p className={cn("text-slate-300 leading-relaxed", isRejected && "line-through text-slate-600")}>
        {patch.description}
      </p>

      {/* Diff preview */}
      {patch.section === "experience" && patch.bullet_old && patch.bullet_new && (
        <div className="space-y-1">
          <div className="flex items-start gap-1.5 text-red-400/80">
            <span className="shrink-0 font-mono font-bold mt-0.5">−</span>
            <span className="line-through opacity-75">{patch.bullet_old}</span>
          </div>
          <div className="flex items-start gap-1.5 text-emerald-400/90">
            <span className="shrink-0 font-mono font-bold mt-0.5">+</span>
            <span>{patch.bullet_new}</span>
          </div>
        </div>
      )}

      {patch.section === "summary" && patch.new_summary && (
        <div className="flex items-start gap-1.5 text-emerald-400/90">
          <ChevronRight className="w-3 h-3 shrink-0 mt-0.5" />
          <span className="line-clamp-4">{patch.new_summary}</span>
        </div>
      )}

      {patch.section === "skills" && (
        <div className="space-y-0.5">
          {(patch.add_skills ?? []).length > 0 && (
            <div className="flex flex-wrap gap-1">
              {patch.add_skills!.map((s) => (
                <span key={s} className="bg-emerald-400/15 text-emerald-300 px-1.5 py-0.5 rounded text-[10px]">
                  + {s}
                </span>
              ))}
            </div>
          )}
          {(patch.remove_skills ?? []).length > 0 && (
            <div className="flex flex-wrap gap-1">
              {patch.remove_skills!.map((s) => (
                <span key={s} className="bg-red-400/15 text-red-300 px-1.5 py-0.5 rounded text-[10px] line-through">
                  − {s}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Accept / Reject buttons */}
      {status === "pending" && (
        <div className="flex gap-1.5 pt-0.5">
          <button
            type="button"
            onClick={onAccept}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-colors"
          >
            <Check className="w-3 h-3" />
            Apply
          </button>
          <button
            type="button"
            onClick={onReject}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 font-semibold transition-colors"
          >
            <X className="w-3 h-3" />
            Skip
          </button>
        </div>
      )}
      {status === "accepted" && (
        <p className="text-emerald-400 font-semibold flex items-center gap-1">
          <Check className="w-3 h-3" /> Applied to resume
        </p>
      )}
      {status === "rejected" && (
        <p className="text-slate-500 flex items-center gap-1">
          <X className="w-3 h-3" /> Skipped
        </p>
      )}
    </div>
  );
}

// ── Chat bubble ──────────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] bg-amber-400 text-slate-900 rounded-2xl rounded-tr-sm px-3 py-2 text-sm font-medium leading-relaxed">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({
  message,
  onAcceptPatch,
  onRejectPatch,
}: {
  message: AssistantMessage;
  onAcceptPatch: (idx: number) => void;
  onRejectPatch: (idx: number) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-2">
        <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center shrink-0 mt-0.5">
          <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
        </div>
        <div className="flex-1 text-slate-300 text-sm leading-relaxed bg-slate-800/50 rounded-2xl rounded-tl-sm px-3 py-2">
          {message.content}
        </div>
      </div>
      {message.patches.length > 0 && (
        <div className="ml-8 space-y-2">
          {message.patches.map((patch, i) => (
            <PatchCard
              key={i}
              patch={patch}
              status={message.patchStatuses[i]}
              onAccept={() => onAcceptPatch(i)}
              onReject={() => onRejectPatch(i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Typing indicator ─────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-start gap-2">
      <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center shrink-0">
        <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
      </div>
      <div className="bg-slate-800/50 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
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

// ── Main component ───────────────────────────────────────────────────────────

interface Props {
  sessionId: string;
  tailored: TailoredResumeOutput | null;
  onApplyPatch: (patch: ResumePatch, updatedTailored: TailoredResumeOutput) => void;
}

export function ResumeChat({ sessionId, tailored, onApplyPatch }: Props) {
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function buildHistory(): ChatMessage[] {
    return messages.map((m) => ({ role: m.role, content: m.content }));
  }

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const res: ChatResponse = await chatWithResume(sessionId, {
        message: text,
        history: buildHistory(),
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.reply,
          patches: res.patches,
          patchStatuses: res.patches.map(() => "pending" as PatchStatus),
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong. Please try again.",
          patches: [],
          patchStatuses: [],
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }

  function applyPatch(msgIdx: number, patchIdx: number) {
    if (!tailored) return;

    const msg = messages[msgIdx];
    if (msg.role !== "assistant") return;

    const patch = msg.patches[patchIdx];
    let updated: TailoredResumeOutput = { ...tailored };

    if (patch.section === "summary" && patch.new_summary) {
      updated = { ...updated, summary: patch.new_summary };
    }

    if (patch.section === "skills") {
      let skills = [...(updated.skills ?? [])];
      if (patch.add_skills?.length) {
        const toAdd = patch.add_skills.filter((s) => !skills.includes(s));
        skills = [...skills, ...toAdd];
      }
      if (patch.remove_skills?.length) {
        const removeSet = new Set(patch.remove_skills);
        skills = skills.filter((s) => !removeSet.has(s));
      }
      updated = { ...updated, skills };
    }

    if (patch.section === "experience" && patch.company && patch.bullet_old && patch.bullet_new) {
      const experience = updated.experience.map((exp) => {
        if (exp.company !== patch.company) return exp;
        const bullets = exp.bullets.map((b) =>
          b === patch.bullet_old ? patch.bullet_new! : b,
        );
        return { ...exp, bullets };
      });
      updated = { ...updated, experience };
    }

    // Mark the patch as accepted in the UI
    setMessages((prev) =>
      prev.map((m, mi) => {
        if (mi !== msgIdx || m.role !== "assistant") return m;
        const patchStatuses = [...m.patchStatuses];
        patchStatuses[patchIdx] = "accepted";
        return { ...m, patchStatuses };
      }),
    );

    onApplyPatch(patch, updated);
  }

  function rejectPatch(msgIdx: number, patchIdx: number) {
    setMessages((prev) =>
      prev.map((m, mi) => {
        if (mi !== msgIdx || m.role !== "assistant") return m;
        const patchStatuses = [...m.patchStatuses];
        patchStatuses[patchIdx] = "rejected";
        return { ...m, patchStatuses };
      }),
    );
  }

  const noResume = !tailored;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8 space-y-3">
            <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center mx-auto">
              <MessageSquare className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p className="text-slate-300 text-sm font-medium">Resume Chat</p>
              <p className="text-slate-500 text-xs mt-1 leading-relaxed">
                Ask me to make targeted edits — strengthen a bullet, add a keyword, rewrite your summary, or adjust the tone.
              </p>
            </div>
            <div className="space-y-1.5 text-left">
              {[
                "Add a metric to my Oracle bullet at IBM",
                "Rewrite my summary to sound more senior",
                "Add Snowflake to my skills",
                "Make my experience section more technical",
              ].map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => { setInput(ex); inputRef.current?.focus(); }}
                  className="w-full text-left text-xs text-slate-400 hover:text-amber-400 bg-slate-800/50 hover:bg-slate-800 border border-slate-700/50 rounded-lg px-3 py-2 transition-colors"
                >
                  &ldquo;{ex}&rdquo;
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, msgIdx) =>
          msg.role === "user" ? (
            <UserBubble key={msgIdx} content={msg.content} />
          ) : (
            <AssistantBubble
              key={msgIdx}
              message={msg}
              onAcceptPatch={(patchIdx) => applyPatch(msgIdx, patchIdx)}
              onRejectPatch={(patchIdx) => rejectPatch(msgIdx, patchIdx)}
            />
          ),
        )}

        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-slate-700/60 p-3 space-y-2">
        {noResume && (
          <p className="text-xs text-amber-400/80 bg-amber-400/10 border border-amber-400/20 rounded-lg px-2 py-1.5">
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
            }}
            disabled={loading || noResume}
            placeholder={noResume ? "Run rewrite first…" : "Ask me to change anything… (Enter to send)"}
            rows={2}
            className="flex-1 resize-none bg-slate-800 border border-slate-700 focus:border-amber-400/60 rounded-xl px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none transition-colors disabled:opacity-40 leading-relaxed"
          />
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
        <p className="text-[10px] text-slate-600">Shift+Enter for new line · Enter to send</p>
      </div>
    </div>
  );
}
