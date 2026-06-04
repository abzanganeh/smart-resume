import Image from "next/image";

type ProductScreenshotProps = {
  className?: string;
  priority?: boolean;
};

/** Product marketing shot — served from `/marketing/smart-resume-photo-03.jpg`. */
export function ProductScreenshot({
  className = "w-full h-auto rounded-xl border border-slate-700/80 shadow-2xl shadow-black/40",
  priority = false,
}: ProductScreenshotProps) {
  return (
    <Image
      src="/marketing/smart-resume-photo-03.jpg"
      alt="Smart Resume Agent tailoring a resume to a job description with ATS guidance"
      width={1200}
      height={655}
      className={className}
      priority={priority}
    />
  );
}
