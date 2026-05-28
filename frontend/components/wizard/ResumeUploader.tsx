"use client";

import { useCallback, useState } from "react";
import { Upload, FileText, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadResumeFile, pasteResumeText, type ParsedResume } from "@/lib/api";

interface Props {
  sessionId: string;
  onParsed: (parsed: ParsedResume) => void;
}

export function ResumeUploader({ sessionId, onParsed }: Props) {
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (file.size > 5 * 1024 * 1024) {
        setError("File exceeds 5MB limit.");
        return;
      }
      const allowed = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"];
      if (!allowed.includes(file.type)) {
        setError("Only PDF, DOCX, and TXT files are supported.");
        return;
      }
      setLoading(true);
      try {
        const result = await uploadResumeFile(sessionId, file);
        onParsed(result.parsed);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Upload failed.");
      } finally {
        setLoading(false);
      }
    },
    [sessionId, onParsed]
  );

  const handlePaste = async () => {
    if (!pasteText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await pasteResumeText(sessionId, pasteText);
      onParsed(result.parsed);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to process resume text.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setMode("upload")}
          className={cn("px-4 py-2 rounded-lg text-sm font-medium transition-colors", mode === "upload" ? "bg-amber-400 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700")}
        >
          Upload file
        </button>
        <button
          onClick={() => setMode("paste")}
          className={cn("px-4 py-2 rounded-lg text-sm font-medium transition-colors", mode === "paste" ? "bg-amber-400 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700")}
        >
          Paste text
        </button>
      </div>

      {mode === "upload" ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
          className={cn(
            "border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors",
            dragging ? "border-amber-400 bg-amber-400/5" : "border-slate-700 hover:border-slate-500"
          )}
          onClick={() => document.getElementById("resume-file-input")?.click()}
        >
          <Upload className="w-10 h-10 text-slate-500 mx-auto mb-3" />
          <p className="text-slate-300 font-medium">Drop your resume here</p>
          <p className="text-slate-500 text-sm mt-1">PDF, DOCX, or TXT · Max 5MB</p>
          <input
            id="resume-file-input"
            type="file"
            accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
        </div>
      ) : (
        <div className="space-y-3">
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="Paste your resume text here…"
            className="w-full h-64 bg-slate-800 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600"
          />
          <div className="flex items-center justify-between">
            <span className="text-slate-500 text-xs">{pasteText.length.toLocaleString()} / 15,000 chars</span>
            <button
              onClick={handlePaste}
              disabled={!pasteText.trim() || loading}
              className="px-5 py-2 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors text-sm"
            >
              {loading ? "Parsing…" : "Parse resume"}
            </button>
          </div>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          Parsing resume with AI…
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
}
