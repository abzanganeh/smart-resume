"use client";

import { useState } from "react";
import { Download, Copy, FileText, File } from "lucide-react";
import { exportUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
  disabled?: boolean;
}

export function ExportButtons({ sessionId, disabled }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const url = exportUrl(sessionId, "txt");
    const res = await fetch(url);
    const text = await res.text();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const btnCls = "flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-colors disabled:opacity-40";

  return (
    <div className="flex flex-wrap gap-3">
      <a
        href={disabled ? undefined : exportUrl(sessionId, "pdf")}
        download="tailored_resume.pdf"
        className={cn(btnCls, disabled ? "pointer-events-none opacity-40 bg-amber-400 text-slate-900" : "bg-amber-400 text-slate-900 hover:bg-amber-300")}
      >
        <Download className="w-4 h-4" />
        Download PDF
      </a>
      <a
        href={disabled ? undefined : exportUrl(sessionId, "docx")}
        download="tailored_resume.docx"
        className={cn(btnCls, disabled ? "pointer-events-none opacity-40 bg-slate-700 text-slate-300" : "bg-slate-700 text-slate-300 hover:bg-slate-600")}
      >
        <File className="w-4 h-4" />
        Download DOCX
      </a>
      <a
        href={disabled ? undefined : exportUrl(sessionId, "txt")}
        download="tailored_resume.txt"
        className={cn(btnCls, "bg-slate-800 text-slate-400 hover:bg-slate-700", disabled && "pointer-events-none opacity-40")}
      >
        <FileText className="w-4 h-4" />
        Plain text
      </a>
      <button
        onClick={handleCopy}
        disabled={disabled}
        className={cn(btnCls, "bg-slate-800 text-slate-400 hover:bg-slate-700")}
      >
        <Copy className="w-4 h-4" />
        {copied ? "Copied!" : "Copy to clipboard"}
      </button>
    </div>
  );
}
