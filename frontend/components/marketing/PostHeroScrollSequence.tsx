"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Compass, FileSearch, ShieldCheck } from "lucide-react";
import { PRODUCT_NAME } from "@/lib/brand";
import { formatSignupCreditsCopy } from "@/lib/freeTier";
import { titleFitBar, titleFitLabel } from "@/lib/jobs";
import {
  POST_HERO_TRACK_VH,
  postHeroMotion,
} from "@/lib/marketing/postHeroSequence";
import {
  PINNED_PANEL_HEIGHT_CLASS,
  PINNED_STICKY_TOP_CLASS,
  PINNED_STICKY_TOP_PX,
} from "@/lib/marketing/scrollPin";
import { pinnedProgressForSticky } from "@/lib/marketing/stageRail";
import {
  FINE_PRINT,
  ILLUSTRATIVE_NOTE,
  INLINE_CTA,
  PRIMARY_CTA,
  SECONDARY_CTA,
} from "./styles";

const EXAMPLE_TITLES = [
  { title: "Backend Engineer", score: 92 },
  { title: "Platform Engineer", score: 86 },
  { title: "Data Engineer", score: 79 },
  { title: "Solutions Engineer", score: 71 },
] as const;

function layerTransform(x: number, y: number): string {
  return `translate3d(${x}%, ${y}vh, 0)`;
}

export function PostHeroScrollSequence({
  startingCredits,
}: {
  startingCredits: number;
}) {
  const creditsLabel = startingCredits === 1 ? "credit" : "credits";
  const trackRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(motionQuery.matches);
    apply();
    motionQuery.addEventListener("change", apply);
    return () => motionQuery.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;

    const sync = () => {
      if (frameRef.current !== null) return;
      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = null;
        const track = trackRef.current;
        if (!track) return;

        const rect = track.getBoundingClientRect();
        setProgress(
          pinnedProgressForSticky(
            { top: rect.top, height: rect.height },
            window.innerHeight,
            PINNED_STICKY_TOP_PX,
          ),
        );
      });
    };

    sync();
    window.addEventListener("scroll", sync, { passive: true });
    window.addEventListener("resize", sync, { passive: true });
    return () => {
      window.removeEventListener("scroll", sync);
      window.removeEventListener("resize", sync);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [reducedMotion]);

  if (reducedMotion) {
    return (
      <div className="mx-auto max-w-3xl space-y-12 px-4 py-16 sm:px-6">
        <CtaPanel startingCredits={startingCredits} creditsLabel={creditsLabel} />
        <RolesPanel />
        <ProofPanel />
      </div>
    );
  }

  const motion = postHeroMotion(progress);

  return (
    <>
      <div
        ref={trackRef}
        className="post-hero-sequence-track relative w-full"
        data-post-hero-sequence
        data-post-hero-progress={progress.toFixed(3)}
        style={{ height: `${POST_HERO_TRACK_VH}vh` }}
      >
        <div
          className={`post-hero-sequence-stage sticky ${PINNED_STICKY_TOP_CLASS} ${PINNED_PANEL_HEIGHT_CLASS} overflow-hidden bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800`}
        >
          <div
            className="post-hero-sequence-layer absolute inset-0 flex items-center justify-center px-4 sm:px-6"
            style={{
              opacity: motion.cta.opacity,
              transform: layerTransform(motion.cta.x, motion.cta.y),
              pointerEvents: motion.cta.opacity > 0.2 ? "auto" : "none",
            }}
            aria-hidden={motion.cta.opacity < 0.05}
          >
            <CtaPanel startingCredits={startingCredits} creditsLabel={creditsLabel} />
          </div>

          <div
            className="post-hero-sequence-layer absolute inset-0 flex items-center justify-center px-4 sm:px-6"
            style={{
              opacity: motion.roles.opacity,
              transform: layerTransform(motion.roles.x, motion.roles.y),
              pointerEvents: motion.roles.opacity > 0.2 ? "auto" : "none",
            }}
            aria-hidden={motion.roles.opacity < 0.05}
          >
            <RolesPanel />
          </div>

          <div
            className="post-hero-sequence-layer absolute inset-0 flex items-center justify-center px-4 sm:px-6"
            style={{
              opacity: motion.proof.opacity,
              transform: layerTransform(motion.proof.x, motion.proof.y),
              pointerEvents: motion.proof.opacity > 0.2 ? "auto" : "none",
            }}
            aria-hidden={motion.proof.opacity < 0.05}
          >
            <ProofPanel />
          </div>
        </div>
      </div>
    </>
  );
}

function CtaPanel({
  startingCredits,
  creditsLabel,
}: {
  startingCredits: number;
  creditsLabel: string;
}) {
  return (
    <section
      aria-label="Get started"
      className="marketing-hero-cta w-full max-w-3xl rounded-2xl border border-slate-200/80 bg-white/95 px-5 py-10 text-center shadow-lg backdrop-blur-sm sm:px-8 sm:py-12 dark:border-slate-700/80 dark:bg-slate-900/95"
    >
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-8">
        <div className="flex w-full flex-col items-center justify-center gap-4 sm:flex-row sm:gap-5">
          <Link href="/auth?mode=register" className={PRIMARY_CTA}>
            Start your career story
            <ArrowRight aria-hidden className="h-5 w-5" />
          </Link>
          <Link href="/checkup" className={SECONDARY_CTA}>
            <FileSearch aria-hidden className="h-4 w-4" />
            Check a resume free
          </Link>
        </div>

        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-1.5 text-sm text-emerald-800 dark:border-emerald-700/50 dark:bg-emerald-900/30 dark:text-emerald-300">
          <Compass aria-hidden className="h-4 w-4" />
          Included on the free plan
        </div>

        <div className="space-y-3 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-3xl">
            You don&rsquo;t have to know what to search for.
          </h2>
          <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400 sm:text-base">
            Once your master resume exists, {PRODUCT_NAME}{" "}
            reads it and proposes ten realistic job titles &mdash; each with a fit
            score and the strengths and gaps behind it.
          </p>
        </div>

        <div className="space-y-3 border-t border-slate-200 pt-6 dark:border-slate-700">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {formatSignupCreditsCopy(startingCredits)} · No credit card required
          </p>
          <p className={`mx-auto max-w-xl leading-relaxed ${FINE_PRINT}`}>
            Free plans watch one company and check it every 30 minutes; paid plans
            watch more, more often. Registering takes about a minute and includes{" "}
            {startingCredits} AI {creditsLabel}. The resume checkup needs no account at
            all.
          </p>
        </div>
      </div>
    </section>
  );
}

function RolesPanel() {
  return (
    <div className="w-full max-w-2xl rounded-2xl border border-slate-300 bg-white/95 p-6 shadow-lg dark:border-slate-700 dark:bg-slate-900/95 sm:p-8">
      <div className="mb-5 flex items-baseline justify-between gap-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Suggested roles
        </h3>
        <span className={ILLUSTRATIVE_NOTE}>
          Illustrative example &mdash; your titles come from your own resume
        </span>
      </div>

      <ul className="space-y-3">
        {EXAMPLE_TITLES.map((role) => (
          <li
            key={role.title}
            className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-4"
          >
            <span className="shrink-0 text-sm font-medium text-slate-900 dark:text-slate-100 sm:w-48">
              {role.title}
            </span>
            <span
              aria-hidden
              className="font-mono text-xs tracking-tighter text-amber-700 dark:text-amber-400"
            >
              {titleFitBar(role.score, 16)}
            </span>
            <span className="text-xs tabular-nums text-slate-600 dark:text-slate-400">
              {titleFitLabel(role.score)}
            </span>
          </li>
        ))}
        <li className={`${FINE_PRINT} pt-1`}>…and six more, ranked by fit.</li>
      </ul>

      <div className="mt-6 border-t border-slate-300 pt-5 dark:border-slate-700">
        <Link href="/auth?mode=register" className={INLINE_CTA}>
          Discover my career options
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}

const SCORE_PROOF = [
  { label: "Your resume as-is", score: 54, tone: "before" as const },
  { label: "After tailoring", score: 88, tone: "after" as const },
];

const HONESTY_RULES = [
  "Must-have keywords are lifted verbatim from the posting, then matched against experience you actually wrote.",
  "A missing metric gets flagged for you to fill in — never invented to lift the score.",
  "Titles, employers, and dates are never rewritten.",
];

function ProofPanel() {
  return (
    <div className="w-full max-w-2xl rounded-2xl border border-slate-300 bg-white/95 p-6 shadow-lg dark:border-slate-700 dark:bg-slate-900/95 sm:p-8">
      <div className="mb-5 flex items-baseline justify-between gap-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Why the numbers hold up
        </h3>
        <span className={ILLUSTRATIVE_NOTE}>
          Illustrative scores &mdash; yours come from your own resume
        </span>
      </div>

      <h2 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-3xl">
        The ATS score is computed in code, not guessed by a model.
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400 sm:text-base">
        Every version runs through the same scoring engine, so a before-and-after
        is a real measurement you can repeat &mdash; not a second opinion.
      </p>

      <dl className="mt-6 space-y-3">
        {SCORE_PROOF.map((entry) => (
          <div
            key={entry.label}
            className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-4"
          >
            <dt className="shrink-0 text-sm font-medium text-slate-900 dark:text-slate-100 sm:w-40">
              {entry.label}
            </dt>
            <dd className="flex items-center gap-3">
              <span
                aria-hidden
                className={`font-mono text-xs tracking-tighter ${
                  entry.tone === "after"
                    ? "text-emerald-700 dark:text-emerald-400"
                    : "text-slate-500 dark:text-slate-500"
                }`}
              >
                {titleFitBar(entry.score, 16)}
              </span>
              <span className="text-xs tabular-nums text-slate-600 dark:text-slate-400">
                {entry.score} / 100
              </span>
            </dd>
          </div>
        ))}
      </dl>

      <ul className="mt-6 space-y-2 border-t border-slate-300 pt-5 dark:border-slate-700">
        {HONESTY_RULES.map((rule) => (
          <li
            key={rule}
            className="flex gap-2 text-sm leading-snug text-slate-600 dark:text-slate-400"
          >
            <ShieldCheck
              aria-hidden
              className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700 dark:text-emerald-400"
            />
            {rule}
          </li>
        ))}
      </ul>

      <div className="mt-6 flex flex-col gap-2">
        <Link href="/checkup" className={INLINE_CTA}>
          Score a resume free
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
        <p className={FINE_PRINT}>No account needed for the checkup.</p>
      </div>
    </div>
  );
}
