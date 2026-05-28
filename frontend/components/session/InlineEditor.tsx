"use client";

import { useState } from "react";
import { Edit2, Check, X } from "lucide-react";
import { patchTailoredResume } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
  section: string;
  company?: string;
  bulletIndex?: number;
  currentText: string;
  onSaved: (newText: string, version: number) => void;
}

export function InlineEditor({ sessionId, section, company, bulletIndex, currentText, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(currentText);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const result = await patchTailoredResume(sessionId, {
        section,
        company,
        bullet_index: bulletIndex,
        new_text: text,
      });
      onSaved(text, result.version);
      setEditing(false);
    } catch {
      // keep editing open on error
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="group flex items-start gap-2">
        <p className="text-slate-200 text-sm flex-1">{text}</p>
        <button
          onClick={() => setEditing(true)}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-amber-400"
          title="Edit this bullet"
        >
          <Edit2 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoFocus
        className="w-full bg-slate-800 border border-amber-400/50 rounded-lg px-3 py-2 text-slate-200 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
        rows={3}
      />
      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-400 text-slate-900 rounded-md text-xs font-semibold hover:bg-amber-300 disabled:opacity-40"
        >
          <Check className="w-3 h-3" />
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={() => { setText(currentText); setEditing(false); }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 text-slate-300 rounded-md text-xs hover:bg-slate-600"
        >
          <X className="w-3 h-3" />
          Cancel
        </button>
      </div>
    </div>
  );
}
