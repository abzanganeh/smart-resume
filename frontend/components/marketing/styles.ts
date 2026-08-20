/** Shared CTA and section classes so landing sections stay visually consistent. */

export const PRIMARY_CTA =
  "inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold px-8 py-3.5 rounded-lg hover:bg-amber-300 transition-colors text-lg";

export const SECONDARY_CTA =
  "inline-flex items-center gap-2 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-slate-500 hover:text-slate-900 dark:hover:text-white font-medium px-6 py-3.5 rounded-lg transition-colors text-base";

export const INLINE_CTA =
  "inline-flex items-center gap-1.5 text-sm font-medium text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 transition-colors";

export const SECTION = "max-w-5xl mx-auto px-6";

export const SECTION_HEADING =
  "text-center text-2xl font-semibold mb-3 text-slate-800 dark:text-slate-200";

export const SECTION_SUBHEADING =
  "text-center text-slate-600 dark:text-slate-400 text-sm mb-12 max-w-2xl mx-auto";

/**
 * Marks example content as illustrative — required by the no-fabrication rule.
 * Deliberately uses the same contrast tier as body copy: this label carries a
 * correctness claim, so it must not be the least legible text on the page.
 */
export const ILLUSTRATIVE_NOTE =
  "text-xs text-slate-600 dark:text-slate-400 italic";

/** Secondary note that still has to clear AA at 12px (credit costs, gating). */
export const FINE_PRINT = "text-xs text-slate-600 dark:text-slate-400";
