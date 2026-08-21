import Image from "next/image";

type ProductScreenshotProps = {
  className?: string;
  priority?: boolean;
};

/**
 * Product marketing shot — served from `/marketing/taliocv-hero.jpg`.
 *
 * `unoptimized` is load-bearing, not an oversight. Next's image optimizer
 * requires `sharp` in production, and this project does not install it: it is
 * absent from `node_modules` and from `.next/standalone/node_modules`, which is
 * all the runner stage of `frontend/Dockerfile` copies. Dropping the flag would
 * make the hero image 500 in the deployed app to save roughly 170KB on a 236KB
 * file. Revisit by adding `sharp` as a dependency first, then verifying the
 * built image serves `/_next/image` before removing this.
 */
export function ProductScreenshot({
  className = "w-full h-auto rounded-xl border border-slate-300 dark:border-slate-700/80 shadow-2xl shadow-black/40",
  priority = false,
}: ProductScreenshotProps) {
  return (
    <Image
      src="/marketing/taliocv-hero.jpg?v=3"
      alt="TalioCV — AI resume tailoring and ATS optimization, framed brand mockup"
      width={1536}
      height={1024}
      className={className}
      priority={priority}
      unoptimized
    />
  );
}
