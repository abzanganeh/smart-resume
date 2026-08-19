"use client";

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

interface Props {
  left: ReactNode;
  right: ReactNode;
  storageKey: string;
  defaultRightWidth?: number;
  minRightWidth?: number;
  maxRightWidth?: number;
  minLeftWidth?: number;
  className?: string;
}

function readStoredWidth(key: string, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function ResizableSplit({
  left,
  right,
  storageKey,
  defaultRightWidth = 360,
  minRightWidth = 280,
  maxRightWidth = 720,
  minLeftWidth = 360,
  className = "",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [rightWidth, setRightWidth] = useState(() =>
    readStoredWidth(storageKey, defaultRightWidth),
  );
  const [isLarge, setIsLarge] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const sync = () => setIsLarge(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!isLarge) return;
    try {
      localStorage.setItem(storageKey, String(rightWidth));
    } catch {
      // ignore quota / private mode
    }
  }, [isLarge, rightWidth, storageKey]);

  const clampWidth = useCallback(
    (next: number) => {
      const container = containerRef.current;
      const handle = 10;
      const maxByContainer = container
        ? container.offsetWidth - minLeftWidth - handle
        : maxRightWidth;
      const max = Math.min(maxRightWidth, maxByContainer);
      return Math.max(minRightWidth, Math.min(max, next));
    },
    [maxRightWidth, minLeftWidth, minRightWidth],
  );

  useEffect(() => {
    if (!isLarge) return;

    function onMove(e: MouseEvent) {
      if (!dragRef.current) return;
      const delta = e.clientX - dragRef.current.startX;
      setRightWidth(clampWidth(dragRef.current.startWidth - delta));
    }

    function onUp() {
      dragRef.current = null;
      setIsDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [clampWidth, isLarge]);

  function startDrag(e: React.MouseEvent) {
    if (!isLarge) return;
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startWidth: rightWidth };
    setIsDragging(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function resetWidth() {
    setRightWidth(defaultRightWidth);
  }

  return (
    <div
      ref={containerRef}
      className={`flex flex-col lg:flex-row lg:items-stretch gap-6 lg:gap-0 ${className}`}
    >
      <div className="flex-1 min-w-0">{left}</div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panels"
        title="Drag to resize · double-click to reset"
        onMouseDown={startDrag}
        onDoubleClick={resetWidth}
        className={`hidden lg:flex w-2.5 shrink-0 items-center justify-center cursor-col-resize group touch-none ${
          isDragging ? "bg-amber-500/20 dark:bg-amber-400/20" : ""
        }`}
      >
        <div className="w-1 h-16 rounded-full bg-slate-200 dark:bg-slate-700 group-hover:bg-amber-400/70 transition-colors" />
      </div>

      <div
        className="w-full lg:shrink-0 flex flex-col min-h-[480px]"
        style={isLarge ? { width: rightWidth } : undefined}
      >
        {right}
      </div>
    </div>
  );
}
