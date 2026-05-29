"use client";

import { useEffect, useRef } from "react";
import { CheckCircle2 } from "lucide-react";

interface Props {
  messages: string[];
  done: boolean;
}

/**
 * Displays a streaming list of progress steps so the user can see exactly what
 * the AI assistant is doing instead of staring at a spinner.
 */
export function ProgressLog({ messages, done }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (!messages.length) {
    return (
      <div className="flex flex-col items-center gap-3 py-10 text-slate-400">
        <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Starting up…</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/70 border border-slate-700 rounded-xl p-4 space-y-2 max-h-56 overflow-y-auto">
      {messages.map((msg, i) => {
        const isLast = i === messages.length - 1;
        const isDone = done && isLast;
        return (
          <div key={i} className="flex items-start gap-2.5 text-sm">
            {isDone ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : isLast && !done ? (
              <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-slate-600 shrink-0 mt-0.5" />
            )}
            <span className={isLast && !done ? "text-slate-200" : "text-slate-500"}>
              {msg}
            </span>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
