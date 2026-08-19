import Image from "next/image";

const MARK_SRC = "/brand/mark.png";
/** Cropped transparent lockup from `/brand/taliocv-2.svg`. */
const LOCKUP_SRC = "/brand/taliocv-2-lockup.png";
const MARK_SIZE = 512;
const LOCKUP_W = 672;
const LOCKUP_H = 264;

type BrandLogoProps = {
  className?: string;
  /** Prioritize LCP on above-the-fold pages (landing, auth). */
  priority?: boolean;
  /** Show wordmark beside the icon (nav, auth). */
  showWordmark?: boolean;
};

/** TalioCV lockup from taliocv-2.svg or icon-only `/brand/mark.png`. */
export function BrandLogo({
  className = "h-10 w-auto",
  priority = false,
  showWordmark = true,
}: BrandLogoProps) {
  if (showWordmark) {
    return (
      <Image
        src={LOCKUP_SRC}
        alt="TalioCV"
        width={LOCKUP_W}
        height={LOCKUP_H}
        className={className}
        priority={priority}
        unoptimized
      />
    );
  }

  return (
    <Image
      src={MARK_SRC}
      alt="TalioCV"
      width={MARK_SIZE}
      height={MARK_SIZE}
      className={className}
      priority={priority}
      unoptimized
    />
  );
}
