"use client";

/**
 * StoryModeSelector — shown before any recording begins.
 *
 * Lets the user choose between two Story Mode flows:
 *   "free"       — record segments freely, optional per-segment coaching
 *   "interview"  — AI asks structured career questions, user answers each one
 */

import { BookOpen, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

export type StoryMode = "free" | "interview";

interface ModeCard {
  id: StoryMode;
  icon: React.ReactNode;
  title: string;
  tagline: string;
  bullets: string[];
  cost: string;
  costColor: string;
}

const MODES: ModeCard[] = [
  {
    id: "free",
    icon: <BookOpen className="w-6 h-6" />,
    title: "Tell your story",
    tagline: "Record your career in your own words",
    bullets: [
      "Record up to 30 × 60-second segments",
      "Edit each segment before generating",
      "Optional per-segment AI coaching",
      "Generate resume when ready",
    ],
    cost: "Free (Chrome/Edge) · 2 credits (Firefox/Safari)",
    costColor: "text-emerald-400",
  },
  {
    id: "interview",
    icon: <MessageSquare className="w-6 h-6" />,
    title: "Coached interview",
    tagline: "AI guides you through structured career questions",
    bullets: [
      "AI asks role, achievements, skills, education…",
      "Follow-up questions when answers lack metrics",
      "Answer by typing or speaking",
      "Resume generated from your complete answers",
    ],
    cost: "1 credit per session (subscribers & BYOK: free)",
    costColor: "text-amber-400",
  },
];

interface Props {
  isFreeUser: boolean;
  onSelect: (mode: StoryMode) => void;
}

export function StoryModeSelector({ isFreeUser, onSelect }: Props) {
  return (
    <div className="space-y-5">
      <div className="text-center space-y-1">
        <h2 className="text-lg font-semibold text-slate-100">
          How would you like to build your resume?
        </h2>
        <p className="text-sm text-slate-400">
          Choose a mode — you can always switch by refreshing.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            onClick={() => onSelect(mode.id)}
            className={cn(
              "group relative text-left rounded-2xl border p-5 space-y-3 transition-all duration-200",
              "border-slate-700 bg-slate-800/40 hover:border-indigo-500/60 hover:bg-indigo-950/20",
              "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900",
            )}
          >
            {/* Icon + title */}
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-slate-700/60 text-indigo-400 group-hover:bg-indigo-900/60 transition-colors">
                {mode.icon}
              </div>
              <div>
                <p className="font-semibold text-slate-100 text-sm">{mode.title}</p>
                <p className="text-xs text-slate-400 mt-0.5">{mode.tagline}</p>
              </div>
            </div>

            {/* Bullets */}
            <ul className="space-y-1.5">
              {mode.bullets.map((b, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                  <span className="mt-0.5 shrink-0 w-1 h-1 rounded-full bg-indigo-400" />
                  {b}
                </li>
              ))}
            </ul>

            {/* Cost */}
            <p className={cn("text-xs font-medium pt-1", mode.costColor)}>
              {mode.id === "interview" && isFreeUser ? (
                <>1 credit per session</>
              ) : (
                mode.cost
              )}
            </p>

            {/* Arrow */}
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-600 group-hover:text-indigo-400 transition-colors">
              →
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
