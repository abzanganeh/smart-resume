import Image from "next/image";

type ProductScreenshotProps = {
  className?: string;
  priority?: boolean;
};

/** Product marketing shot — served from `/marketing/taliocv-hero.jpg`. */
export function ProductScreenshot({
  className = "w-full h-auto rounded-xl border border-slate-300 dark:border-slate-700/80 shadow-2xl shadow-black/40",
  priority = false,
}: ProductScreenshotProps) {
  return (
    <Image
      src="/marketing/taliocv-hero.jpg?v=3"
      alt="TalioCV — AI tailoring and company intel, framed brand mockup"
      width={1536}
      height={1024}
      className={className}
      priority={priority}
      unoptimized
    />
  );
}
