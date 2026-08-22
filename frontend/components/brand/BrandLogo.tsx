import Image from "next/image";
import { PRODUCT_NAME, WORDMARK_LIGHT_SRC } from "@/lib/brand";

const MARK_SRC = "/brand/mark.png";
const MARK_SIZE = 512;
/** Intrinsic size of `flintapply-wordmark-light.png` (2172×724). */
const WORDMARK_W = 2172;
const WORDMARK_H = 724;

type BrandLogoProps = {
  className?: string;
  /** Prioritize LCP on above-the-fold pages (landing, auth). */
  priority?: boolean;
  /** Show wordmark beside the icon (nav, auth). */
  showWordmark?: boolean;
};

/** FlintApply icon + text wordmark, or icon-only `/brand/mark.png`. */
export function BrandLogo({
  className = "h-10 w-auto",
  priority = false,
  showWordmark = true,
}: BrandLogoProps) {
  if (showWordmark) {
    return (
      <Image
        src={WORDMARK_LIGHT_SRC}
        alt={PRODUCT_NAME}
        width={WORDMARK_W}
        height={WORDMARK_H}
        className={className}
        priority={priority}
        unoptimized
      />
    );
  }

  return (
    <Image
      src={MARK_SRC}
      alt={PRODUCT_NAME}
      width={MARK_SIZE}
      height={MARK_SIZE}
      className={className}
      priority={priority}
      unoptimized
    />
  );
}
