import Image from "next/image";

/** Master asset: `Flint/src/assets/flint-logo-resume.png` → `public/brand/logo.png`. */
const LOGO_WIDTH = 1536;
const LOGO_HEIGHT = 1024;

type BrandLogoProps = {
  className?: string;
  /** Prioritize LCP on above-the-fold pages (landing, auth). */
  priority?: boolean;
};

/** Transparent brand mark served from `/brand/logo.png`. */
export function BrandLogo({ className = "h-10 w-auto", priority = false }: BrandLogoProps) {
  return (
    <Image
      src="/brand/logo.png"
      alt="Flint Resume — AI tailoring and company intel"
      width={LOGO_WIDTH}
      height={LOGO_HEIGHT}
      className={className}
      priority={priority}
      unoptimized
    />
  );
}
