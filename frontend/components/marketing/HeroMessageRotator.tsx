"use client";

import { HERO_MESSAGES } from "@/lib/marketing/heroStrengths";

const MESSAGE_COUNT = HERO_MESSAGES.length;

function slideClass(index: number, activeIndex: number): string {
  if (index === activeIndex) return "is-active";
  return "is-idle";
}

interface HeroMessageRotatorProps {
  activeIndex: number;
  /** Full-viewport stack: badge top, copy middle. */
  layout?: "default" | "viewport";
}

/**
 * Full hero message block — badge, headline, tagline, and body.
 * Scroll position drives `activeIndex`; CSS transitions handle the slide/fade.
 */
export function HeroMessageRotator({
  activeIndex,
  layout = "default",
}: HeroMessageRotatorProps) {
  const displayIndex =
    activeIndex >= 0 && activeIndex < MESSAGE_COUNT ? activeIndex : 0;

  const viewport = layout === "viewport";

  const headlineClass = viewport
    ? "hero-message-set__headline text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight leading-tight"
    : "hero-message-set__headline text-4xl sm:text-5xl font-bold tracking-tight mb-5 leading-tight";

  const taglineClass = viewport
    ? "hero-message-set__tagline text-base sm:text-lg text-slate-800 dark:text-slate-200 max-w-2xl mx-auto font-medium leading-snug"
    : "hero-message-set__tagline text-lg sm:text-xl text-slate-700 dark:text-slate-300 mb-3 max-w-2xl mx-auto font-medium";

  const bodyClass = viewport
    ? "hero-message-set__body text-sm sm:text-base text-slate-700 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed"
    : "hero-message-set__body text-lg sm:text-xl text-slate-600 dark:text-slate-400 mb-3 max-w-2xl mx-auto";

  return (
    <div
      className={`hero-message-rotator relative z-[1] mx-auto w-full max-w-3xl text-center${
        viewport ? " hero-message-rotator--viewport flex min-h-0 flex-1 flex-col" : ""
      }`}
    >
      <ul className="sr-only">
        {HERO_MESSAGES.map((message) => (
          <li key={message.id}>
            {message.badge}. {message.headlineLead} {message.headlineAccent}{" "}
            {message.tagline} {message.description}
          </li>
        ))}
      </ul>

      <div
        className="hero-message-rotator__stage"
        data-active-index={displayIndex}
        aria-live="polite"
      >
        {HERO_MESSAGES.map((message, index) => {
          const state = slideClass(index, displayIndex);
          const isActiveHeading = index === displayIndex;

          return (
            <article
              key={message.id}
              className={`hero-message-set hero-message-set--${state}${
                viewport ? " hero-message-set--viewport" : ""
              }`}
              data-message-id={message.id}
              aria-hidden={index === displayIndex ? undefined : true}
            >
              <div className="hero-message-set__badge inline-flex max-w-[min(100%,40rem)] items-center gap-2 rounded-full border border-slate-300/80 bg-white/88 px-3 py-1.5 text-xs backdrop-blur-md dark:border-slate-600/80 dark:bg-slate-900/88 sm:text-sm text-slate-700 dark:text-slate-200 shadow-sm">
                <span
                  aria-hidden
                  className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-600 dark:bg-amber-400"
                />
                <span className="truncate sm:whitespace-normal">{message.badge}</span>
              </div>

              <div
                className={
                  viewport
                    ? "hero-message-set__copy flex min-h-0 flex-1 flex-col justify-center gap-2 px-1 py-3"
                    : undefined
                }
              >
                {isActiveHeading ? (
                  <h1 className={headlineClass}>
                    {message.headlineLead}{" "}
                    <span className="text-amber-700 dark:text-amber-400">
                      {message.headlineAccent}
                    </span>
                  </h1>
                ) : (
                  <p className={headlineClass} aria-hidden>
                    {message.headlineLead}{" "}
                    <span className="text-amber-700 dark:text-amber-400">
                      {message.headlineAccent}
                    </span>
                  </p>
                )}

                <p className={taglineClass}>{message.tagline}</p>
                <p className={bodyClass}>{message.description}</p>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
