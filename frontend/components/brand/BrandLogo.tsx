import Image from "next/image";

const LOGO_WIDTH = 480;
const LOGO_HEIGHT = 262;

type BrandLogoProps = {
  className?: string;
  /** Prioritize LCP on above-the-fold pages (landing, auth). */
  priority?: boolean;
};

/** Transparent brand mark served from `/brand/logo.png`. */
export function BrandLogo({ className = "h-9 w-auto", priority = false }: BrandLogoProps) {
  return (
    <Image
      src="/brand/logo.png"
      alt="Smart Resume Agent — AI-powered job search platform"
      width={LOGO_WIDTH}
      height={LOGO_HEIGHT}
      className={className}
      priority={priority}
    />
  );
}
