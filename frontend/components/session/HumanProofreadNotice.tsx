import { UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  /** Editor = tailor step; export = download / apply step. */
  context: "editor" | "export";
  className?: string;
}

const COPY = {
  editor: {
    title: "Proofread before you submit",
    body:
      "AI can misstate facts, over-insert keywords, or sound unnatural — mistakes are inevitable. " +
      "Read every section yourself, fix wording in the editor (or use ATS hints under each bullet), then export when it sounds like you.",
  },
  export: {
    title: "Human proofread required before you apply",
    body:
      "Scores and suggestions are helpers, not guarantees. Open your download and read it end to end — " +
      "check names, dates, metrics, and tone. Fix anything off in Tailored Rewrite, then download again.",
  },
} as const;

export function HumanProofreadNotice({ context, className }: Props) {
  const { title, body } = COPY[context];

  return (
    <div
      role="note"
      className={cn(
        "rounded-xl border px-4 py-3 text-xs leading-relaxed",
        context === "export"
          ? "border-amber-400/35 bg-amber-500/10 text-amber-950 dark:text-amber-50"
          : "border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 text-slate-700 dark:text-slate-300",
        className,
      )}
    >
      <p className="font-semibold text-slate-900 dark:text-slate-100 mb-1 flex items-center gap-1.5">
        <UserCheck className="w-3.5 h-3.5 shrink-0 text-amber-700 dark:text-amber-400" />
        {title}
      </p>
      <p>{body}</p>
    </div>
  );
}
