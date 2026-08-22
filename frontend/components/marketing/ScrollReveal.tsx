"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Adds `data-revealed="true"` when the block enters the viewport.
 *
 * The default state stays fully visible — only a slight vertical offset moves,
 * so a failed IntersectionObserver cannot blank the section.
 */
export function ScrollReveal({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motion.matches) {
      node.dataset.revealed = "true";
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          node.dataset.revealed = "true";
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={`sr-scroll-reveal ${className}`.trim()}>
      {children}
    </div>
  );
}
