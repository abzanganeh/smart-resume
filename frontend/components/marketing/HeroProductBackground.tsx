import Image from "next/image";
import { HERO_PRODUCT_SHOT_SRC, productScreenshotAlt } from "@/lib/brand";

type HeroProductBackgroundProps = {
  /** 0 = first slide (image most visible); approaches 1 on the last slide. */
  fade?: number;
};

/**
 * Full-bleed product art behind the pinned hero copy. Decorative for sighted
 * users; the alt string satisfies crawlers and assistive summaries.
 */
export function HeroProductBackground({ fade = 0 }: HeroProductBackgroundProps) {
  const imageOpacity = Math.max(0.45, 1 - fade * 0.55);
  const scrimStrength = 0.72 + fade * 0.18;

  return (
    <div
      role="img"
      aria-label={productScreenshotAlt()}
      className="hero-product-background pointer-events-none absolute inset-0 overflow-hidden"
    >
      <Image
        src={HERO_PRODUCT_SHOT_SRC}
        alt=""
        fill
        priority
        unoptimized
        sizes="100vw"
        className="object-cover object-[center_35%] motion-reduce:scale-100 scale-105"
        style={{ opacity: imageOpacity }}
      />
      <div
        className="absolute inset-0 bg-gradient-to-b from-white via-white to-slate-100/95 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900/95"
        style={{ opacity: scrimStrength }}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-white/90 via-transparent to-white/40 dark:from-slate-950/90 dark:to-slate-950/30" />
    </div>
  );
}
