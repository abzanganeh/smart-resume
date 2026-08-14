"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  GraduationCap,
  Info,
  Pencil,
  Plus,
  Redo2,
  RotateCw,
  Save,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import {
  patchTailoredResume,
  type PhaseRunScope,
  type TailoredResumeOutput,
} from "@/lib/api";
import { useVersionStack } from "@/lib/useVersionStack";
import type { ResumeSuggestion } from "@/lib/suggestions";
import {
  acceptedBulletSuggestion,
  acceptedSkillAdds,
  activeSummarySuggestion,
  bulletEditSuggestion,
  datesSuggestion,
  dismissExperienceBulletSuggestions,
  dismissProjectBulletSuggestions,
  dismissNewProjectSuggestions,
  educationBulletAddSuggestions,
  educationSuggestions,
  hasPendingEducationSuggestions,
  experienceSuggestions,
  experienceDeleteSuggestion,
  institutionRenameSuggestion,
  newProjectSuggestions,
  orphanedSuggestions,
  pendingSkillAdds,
  pendingSkillRemoves,
  pendingSuggestionCount,
  projectRemovalPending,
  projectReplaceAllSuggestion,
  projectTitleSuggestion,
  projectDescriptionSuggestion,
  dismissProjectMetaSuggestions,
  skillChipTone,
  skillsSuggestions,
  contactNameSuggestion,
  titleSuggestion,
} from "@/lib/suggestionHighlight";
import {
  InlineFieldSuggestion,
  OrphanSuggestionCard,
  PendingAdditionCard,
  SkillChip,
  SuggestedBulletRow,
  SuggestionActionButtons,
  SummaryHighlight,
} from "./SuggestionHighlight";
import { EntryIssueBadgePill } from "./EntryIssueBadge";
import { entryAnchorKey, resumeAnchorDomId, type EntryIssueBadge } from "@/lib/issueAnchors";

interface Props {
  initial: TailoredResumeOutput;
  sessionId: string;
  /** Bump when the parent replaces tailored output (phase 3, chat, restore). */
  editorSyncKey?: number;
  onSaved?: (updated: TailoredResumeOutput, meta?: { source: "edit" | "undo" | "redo" }) => void;
  onVersionSnapshot?: (version: number) => void;
  onScopedRun?: (scope: PhaseRunScope) => void;
  phaseRunning?: boolean;
  suggestionDraft?: string | null;
  onClearSuggestion?: () => void;
  suggestions?: ResumeSuggestion[];
  onAcceptSuggestion?: (id: string) => void;
  onAcceptAllSuggestions?: () => void;
  onRejectSuggestion?: (id: string) => void;
  onDismissSuggestion?: (id: string) => void;
  entryIssueBadges?: Record<string, EntryIssueBadge>;
}

// ── tiny helpers ─────────────────────────────────────────────────────────────

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 border-b border-slate-700 pb-1.5 mb-3 flex items-center gap-2">
      {title}
      {count !== undefined && (
        <span className="text-slate-600 font-normal normal-case tracking-normal">({count})</span>
      )}
    </h2>
  );
}

function SavedBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-400 font-medium">
      <Check className="w-3 h-3" /> saved
    </span>
  );
}

function dismissAcceptedForSection(
  suggestions: ResumeSuggestion[],
  onDismiss: ((id: string) => void) | undefined,
  predicate: (s: ResumeSuggestion) => boolean,
) {
  if (!onDismiss) return;
  for (const s of suggestions) {
    if (s.status === "accepted" && predicate(s)) onDismiss(s.id);
  }
}

// ── inline text editor ───────────────────────────────────────────────────────

function InlineText({
  value,
  onSave,
  rows = 2,
  placeholder,
}: {
  value: string;
  onSave: (v: string) => Promise<void>;
  rows?: number;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function commit() {
    if (draft.trim() === value.trim()) { setEditing(false); return; }
    setSaving(true);
    await onSave(draft.trim());
    setSaving(false);
    setSaved(true);
    setEditing(false);
    setTimeout(() => setSaved(false), 2000);
  }

  if (!editing) {
    return (
      <div className="group relative">
        <p className="text-slate-200 text-sm leading-relaxed whitespace-pre-wrap pr-8">{value}</p>
        <button
          onClick={() => { setDraft(value); setEditing(true); }}
          className="absolute top-0 right-0 p-1 rounded text-slate-400 hover:text-amber-400 transition opacity-80 hover:opacity-100"
          title="Edit"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        {saved && <SavedBadge />}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <textarea
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={rows}
        placeholder={placeholder}
        className="w-full bg-slate-900 border border-amber-400/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
      />
      <div className="flex gap-2">
        <button
          onClick={commit}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300 disabled:opacity-50"
        >
          <Save className="w-3 h-3" />
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={() => setEditing(false)}
          className="px-3 py-1 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── bullet list editor (reusable for experience AND education) ────────────────

function BulletList({
  bullets,
  onSaveBullet,
  onDeleteBullet,
  onAddBullet,
  addPlaceholder = "Add a bullet…",
}: {
  bullets: string[];
  onSaveBullet: (idx: number, text: string) => Promise<void>;
  onDeleteBullet: (idx: number) => Promise<void>;
  onAddBullet: (text: string) => Promise<void>;
  addPlaceholder?: string;
}) {
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [adding, setAdding] = useState(false);
  const [newBullet, setNewBullet] = useState("");
  const [saving, setSaving] = useState(false);

  async function commitEdit(idx: number) {
    const text = (drafts[idx] ?? bullets[idx]).trim();
    setSaving(true);
    await onSaveBullet(idx, text);
    setSaving(false);
    setEditingIdx(null);
  }

  async function commitDelete(idx: number) {
    setSaving(true);
    await onDeleteBullet(idx);
    setSaving(false);
  }

  async function commitAdd() {
    if (!newBullet.trim()) return;
    setSaving(true);
    await onAddBullet(newBullet.trim());
    setSaving(false);
    setNewBullet("");
    setAdding(false);
  }

  return (
    <div className="space-y-1.5">
      {bullets.map((b, idx) => (
        <div key={idx} className="group flex items-start gap-2">
          {editingIdx === idx ? (
            <div className="flex-1 space-y-1.5">
              <textarea
                autoFocus
                value={drafts[idx] ?? b}
                onChange={(e) => setDrafts((p) => ({ ...p, [idx]: e.target.value }))}
                rows={2}
                className="w-full bg-slate-900 border border-amber-400/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => commitEdit(idx)}
                  disabled={saving}
                  className="flex items-center gap-1 px-3 py-1 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300 disabled:opacity-50"
                >
                  <Save className="w-3 h-3" />
                  {saving ? "…" : "Save"}
                </button>
                <button
                  onClick={() => setEditingIdx(null)}
                  className="px-3 py-1 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <span className="text-slate-500 mt-1 shrink-0">•</span>
              <p className="flex-1 text-slate-200 text-sm leading-relaxed">{b}</p>
              <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition shrink-0">
                <button
                  onClick={() => { setDrafts((p) => ({ ...p, [idx]: b })); setEditingIdx(idx); }}
                  className="p-1 rounded text-slate-500 hover:text-amber-400"
                  title="Edit bullet"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => commitDelete(idx)}
                  className="p-1 rounded text-slate-500 hover:text-red-400"
                  title="Delete bullet"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </>
          )}
        </div>
      ))}

      {adding ? (
        <div className="space-y-1.5 pt-1">
          <textarea
            autoFocus
            value={newBullet}
            onChange={(e) => setNewBullet(e.target.value)}
            placeholder={addPlaceholder}
            rows={2}
            className="w-full bg-slate-900 border border-emerald-500/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-emerald-500 placeholder:text-slate-600"
          />
          <div className="flex gap-2">
            <button
              onClick={commitAdd}
              disabled={saving || !newBullet.trim()}
              className="flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500 disabled:opacity-40"
            >
              <Plus className="w-3 h-3" />
              {saving ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => { setAdding(false); setNewBullet(""); }}
              className="px-3 py-1 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-emerald-400 transition mt-1"
        >
          <Plus className="w-3.5 h-3.5" />
          Add bullet
        </button>
      )}
    </div>
  );
}

function ScopedBulletList({
  bullets,
  company,
  phaseRunning,
  suggestions = [],
  onAcceptSuggestion,
  onRejectSuggestion,
  onRegenBullet,
  onSaveBullet,
  onDeleteBullet,
  onAddBullet,
  addPlaceholder,
}: {
  bullets: string[];
  company: string;
  phaseRunning?: boolean;
  suggestions?: ResumeSuggestion[];
  onAcceptSuggestion?: (id: string) => void;
  onRejectSuggestion?: (id: string) => void;
  onRegenBullet: (idx: number) => void;
  onSaveBullet: (idx: number, text: string) => Promise<void>;
  onDeleteBullet: (idx: number) => Promise<void>;
  onAddBullet: (text: string) => Promise<void>;
  addPlaceholder?: string;
}) {
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [adding, setAdding] = useState(false);
  const [newBullet, setNewBullet] = useState("");
  const [saving, setSaving] = useState(false);

  async function commitEdit(idx: number) {
    const text = (drafts[idx] ?? bullets[idx]).trim();
    setSaving(true);
    await onSaveBullet(idx, text);
    setSaving(false);
    setEditingIdx(null);
  }

  async function commitDelete(idx: number) {
    setSaving(true);
    await onDeleteBullet(idx);
    setSaving(false);
  }

  async function commitAdd() {
    if (!newBullet.trim()) return;
    setSaving(true);
    await onAddBullet(newBullet.trim());
    setSaving(false);
    setNewBullet("");
    setAdding(false);
  }

  return (
    <div className="space-y-1.5">
      {bullets.map((b, idx) => (
        <div key={idx} className="group flex items-start gap-2">
          {editingIdx === idx ? (
            <div className="flex-1 space-y-1.5">
              <textarea
                autoFocus
                value={drafts[idx] ?? b}
                onChange={(e) => setDrafts((p) => ({ ...p, [idx]: e.target.value }))}
                rows={2}
                className="w-full bg-slate-900 border border-amber-400/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => commitEdit(idx)}
                  disabled={saving}
                  className="flex items-center gap-1 px-3 py-1 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300 disabled:opacity-50"
                >
                  <Save className="w-3 h-3" />
                  {saving ? "…" : "Save"}
                </button>
                <button
                  onClick={() => setEditingIdx(null)}
                  className="px-3 py-1 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (() => {
            const editSug = bulletEditSuggestion(suggestions, company, b);
            const acceptedSug = !editSug
              ? acceptedBulletSuggestion(suggestions, company, b)
              : undefined;
            const activeSug = editSug ?? acceptedSug;
            const tone = activeSug?.status === "accepted"
              ? "accepted"
              : activeSug?.status === "pending"
                ? "pending"
                : "none";

            if (activeSug && tone !== "none") {
              return (
                <SuggestedBulletRow
                  suggestion={activeSug}
                  originalText={b}
                  displayText={b}
                  tone={tone}
                  phaseRunning={phaseRunning}
                  onAccept={(id) => onAcceptSuggestion?.(id)}
                  onReject={(id) => onRejectSuggestion?.(id)}
                  onRegen={() => onRegenBullet(idx)}
                  onEdit={() => { setDrafts((p) => ({ ...p, [idx]: b })); setEditingIdx(idx); }}
                  onDelete={() => commitDelete(idx)}
                />
              );
            }

            return (
              <SuggestedBulletRow
                displayText={b}
                tone="none"
                phaseRunning={phaseRunning}
                onAccept={() => {}}
                onReject={() => {}}
                onRegen={() => onRegenBullet(idx)}
                onEdit={() => { setDrafts((p) => ({ ...p, [idx]: b })); setEditingIdx(idx); }}
                onDelete={() => commitDelete(idx)}
              />
            );
          })()}
        </div>
      ))}

      {adding ? (
        <div className="space-y-1.5 pt-1">
          <textarea
            autoFocus
            value={newBullet}
            onChange={(e) => setNewBullet(e.target.value)}
            placeholder={addPlaceholder}
            rows={2}
            className="w-full bg-slate-900 border border-emerald-500/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-emerald-500 placeholder:text-slate-600"
          />
          <div className="flex gap-2">
            <button
              onClick={commitAdd}
              disabled={saving || !newBullet.trim()}
              className="flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500 disabled:opacity-40"
            >
              <Plus className="w-3 h-3" />
              {saving ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => { setAdding(false); setNewBullet(""); }}
              className="px-3 py-1 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-emerald-400 transition mt-1"
        >
          <Plus className="w-3.5 h-3.5" />
          Add bullet
        </button>
      )}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export function TailoredEditor({ initial, sessionId, editorSyncKey = 0, onSaved, onVersionSnapshot, onScopedRun, phaseRunning, suggestionDraft, onClearSuggestion, suggestions = [], onAcceptSuggestion, onAcceptAllSuggestions, onRejectSuggestion, onDismissSuggestion, entryIssueBadges = {} }: Props) {
  function acceptSug(id: string) { onAcceptSuggestion?.(id); }
  function rejectSug(id: string) { onRejectSuggestion?.(id); }

  const { present: data, push, replace, reset, undo, redo, canUndo, canRedo } = useVersionStack(initial);
  const [draftText, setDraftText] = useState(suggestionDraft ?? "");

  useEffect(() => {
    if (suggestionDraft) setDraftText(suggestionDraft);
  }, [suggestionDraft]);
  const [expandedExp, setExpandedExp] = useState<string | null>(
    initial.experience[0]?.company ?? null
  );
  // null = not editing; key = "<company>:title" or "<company>:company"
  const [editingContactName, setEditingContactName] = useState(false);
  const [editingContactValue, setEditingContactValue] = useState("");
  const [editingExpField, setEditingExpField] = useState<string | null>(null);
  const [editingExpValue, setEditingExpValue] = useState("");
  const [editingProjectField, setEditingProjectField] = useState<string | null>(null);
  const [editingProjectValue, setEditingProjectValue] = useState("");
  const [addingProject, setAddingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [newProjectBullets, setNewProjectBullets] = useState("");
  const [editingEduField, setEditingEduField] = useState<string | null>(null);
  const [editingEduValue, setEditingEduValue] = useState("");
  const [expandedEdu, setExpandedEdu] = useState<string | null>(null);
  const [showNotes, setShowNotes] = useState(false);
  const [addMode, setAddMode] = useState<"master" | "manual" | null>(null);
  const [manualSectionText, setManualSectionText] = useState("");
  const [manualTitle, setManualTitle] = useState("Experience");
  const [manualCompany, setManualCompany] = useState("Manual entry");
  const [manualSectionType, setManualSectionType] = useState<
    "experience" | "projects" | "certifications"
  >("experience");

  const initialRef = useRef(initial)
  useEffect(() => {
    initialRef.current = initial
  }, [initial])

  useEffect(() => {
    reset(initialRef.current);
  }, [editorSyncKey, reset]);

  const handleUndo = useCallback(() => {
    const prev = undo();
    if (prev) onSaved?.(prev, { source: "undo" });
  }, [undo, onSaved]);

  const handleRedo = useCallback(() => {
    const next = redo();
    if (next) onSaved?.(next, { source: "redo" });
  }, [redo, onSaved]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if (e.key === "y" || (e.key === "z" && e.shiftKey)) {
        e.preventDefault();
        handleRedo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleUndo, handleRedo]);

  useEffect(() => {
    const pendingExp = data.experience.find((exp) =>
      experienceSuggestions(suggestions, exp.company).some((s) => s.status === "pending"),
    );
    if (pendingExp) setExpandedExp(pendingExp.company);

    const pendingEdu = data.education.find((edu) =>
      hasPendingEducationSuggestions(suggestions, edu.institution, data.education),
    );
    if (pendingEdu) setExpandedEdu(pendingEdu.institution);
  }, [suggestions, data.experience, data.education]);

  async function patch(payload: Record<string, unknown>) {
    const result = await patchTailoredResume(sessionId, payload);
    if (typeof result.version === "number") {
      onVersionSnapshot?.(result.version);
    }
    return result;
  }

  function updateLocal(updater: (prev: TailoredResumeOutput) => TailoredResumeOutput, trackHistory = true) {
    const next = updater(data);
    if (trackHistory) {
      push(next);
    } else {
      replace(next);
    }
    onSaved?.(next);
  }

  function regen(scope: PhaseRunScope) {
    onScopedRun?.(scope);
  }

  async function saveManualSection() {
    if (!manualSectionText.trim() && manualSectionType !== "certifications") return;
    const text = manualSectionText.trim();
    const content = {
      section: manualSectionType,
      title: manualTitle,
      company: manualCompany,
      text,
    };
    await patch({ section_id: "add_section", content });

    if (manualSectionType === "experience") {
      updateLocal((p) => ({
        ...p,
        experience: [
          ...p.experience,
          {
            title: manualTitle,
            company: manualCompany,
            dates: "",
            bullets: [text],
            removed_bullets: [],
            keywords_injected: [],
          },
        ],
      }));
    } else if (manualSectionType === "projects") {
      updateLocal((p) => ({
        ...p,
        projects: [
          ...p.projects,
          { name: manualTitle, description: manualCompany, bullets: [text] },
        ],
      }));
    } else {
      const cert = text || manualTitle.trim();
      if (!cert) return;
      updateLocal((p) => ({
        ...p,
        certifications: p.certifications.includes(cert)
          ? p.certifications
          : [...p.certifications, cert],
      }));
    }

    setManualSectionText("");
    setManualTitle("Experience");
    setManualCompany("Manual entry");
    setManualSectionType("experience");
    setAddMode(null);
  }

  async function deleteExperienceEntry(index: number) {
    await patch({ section: "experience", experience_index: index, delete: true });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.filter((_, i) => i !== index),
    }));
    setExpandedExp(null);
  }

  async function deleteCertification(index: number) {
    await patch({ section: "certifications", cert_index: index, delete: true });
    updateLocal((p) => ({
      ...p,
      certifications: p.certifications.filter((_, i) => i !== index),
    }));
  }

  async function addFromMasterChunk(chunk: { chunk_id: string; section: string; content?: string; score: number }) {
    regen({
      section: chunk.section || "experience",
      mode: "add",
      chunk_id: chunk.chunk_id,
      chunk_content: chunk.content ?? "",
    });
    setAddMode(null);
  }

  const skippedChunks = data.skipped_chunks ?? [];
  const displayName = String(data.contact?.name ?? "").trim();

  // ── Contact ──────────────────────────────────────────────────────────────

  async function saveContactName(name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    await patch({ section: "contact", new_name: trimmed });
    updateLocal((p) => ({
      ...p,
      contact: { ...(p.contact ?? {}), name: trimmed },
    }));
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "contact",
    );
  }

  // ── Summary ──────────────────────────────────────────────────────────────

  async function saveSummary(text: string) {
    await patch({ section: "summary", new_text: text });
    updateLocal((p) => ({ ...p, summary: text }));
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "summary",
    );
  }

  // ── Skills ───────────────────────────────────────────────────────────────

  async function saveSkills(skills: string[]) {
    await patch({ section: "skills", skills });
    updateLocal((p) => ({ ...p, skills }));
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "skills",
    );
  }

  // ── Experience bullets ───────────────────────────────────────────────────

  async function saveExpBullet(company: string, idx: number, text: string) {
    const previousText =
      data.experience.find((e) => e.company === company)?.bullets[idx] ?? "";
    await patch({ section: "experience", company, bullet_index: idx, new_text: text });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company
          ? { ...e, bullets: e.bullets.map((b, i) => (i === idx ? text : b)) }
          : e
      ),
    }));
    dismissExperienceBulletSuggestions(
      suggestions,
      onDismissSuggestion,
      company,
      [previousText, text],
    );
  }

  async function saveExpTitle(company: string, newTitle: string) {
    if (!newTitle.trim()) return;
    await patch({ section: "experience", company, new_title: newTitle.trim() });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company ? { ...e, title: newTitle.trim() } : e
      ),
    }));
  }

  async function saveExpCompany(oldCompany: string, newCompany: string) {
    if (!newCompany.trim() || newCompany.trim() === oldCompany) return;
    await patch({ section: "experience", company: oldCompany, new_company: newCompany.trim() });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === oldCompany ? { ...e, company: newCompany.trim() } : e
      ),
    }));
  }

  async function saveExpDates(company: string, newDates: string) {
    if (!newDates.trim()) return;
    await patch({ section: "experience", company, new_dates: newDates.trim() });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company ? { ...e, dates: newDates.trim() } : e
      ),
    }));
  }

  async function deleteProject(projectIndex: number) {
    await patch({ section: "projects", project_index: projectIndex, delete: true });
    updateLocal((p) => ({
      ...p,
      projects: p.projects.filter((_, i) => i !== projectIndex),
    }));
  }

  async function saveProjectMeta(
    projectIndex: number,
    fields: { new_name?: string; new_description?: string },
  ) {
    await patch({ section: "projects", project_index: projectIndex, ...fields });
    updateLocal((p) => ({
      ...p,
      projects: p.projects.map((proj, i) => {
        if (i !== projectIndex) return proj;
        const next = { ...(proj as Record<string, unknown>) };
        if (fields.new_name !== undefined) next.name = fields.new_name;
        if (fields.new_description !== undefined) next.description = fields.new_description;
        return next;
      }),
    }));
    const project = data.projects[projectIndex] as Record<string, unknown> | undefined;
    const currentName = String(project?.name ?? "").trim();
    if (currentName) {
      dismissProjectMetaSuggestions(suggestions, onDismissSuggestion, currentName);
    }
  }

  async function saveProjectBullet(projectIndex: number, bulletIndex: number, text: string) {
    const project = data.projects[projectIndex] as Record<string, unknown> | undefined;
    const projectName = String(project?.name ?? "").trim();
    const previousText = ((project?.bullets as string[]) ?? [])[bulletIndex] ?? "";
    await patch({
      section: "projects",
      project_index: projectIndex,
      bullet_index: bulletIndex,
      new_text: text,
    });
    updateLocal((p) => ({
      ...p,
      projects: p.projects.map((proj, i) => {
        if (i !== projectIndex) return proj;
        const next = { ...(proj as Record<string, unknown>) };
        const bullets = [...((next.bullets as string[]) ?? [])];
        bullets[bulletIndex] = text;
        next.bullets = bullets;
        return next;
      }),
    }));
    if (projectName) {
      dismissProjectBulletSuggestions(
        suggestions,
        onDismissSuggestion,
        projectName,
        [previousText, text],
      );
    }
  }

  async function deleteProjectBullet(projectIndex: number, bulletIndex: number) {
    const project = data.projects[projectIndex] as Record<string, unknown> | undefined;
    const projectName = String(project?.name ?? "").trim();
    const removedText = ((project?.bullets as string[]) ?? [])[bulletIndex] ?? "";
    await patch({
      section: "projects",
      project_index: projectIndex,
      bullet_index: bulletIndex,
      new_text: "",
    });
    updateLocal((p) => ({
      ...p,
      projects: p.projects.map((proj, i) => {
        if (i !== projectIndex) return proj;
        const next = { ...(proj as Record<string, unknown>) };
        const bullets = ((next.bullets as string[]) ?? []).filter((_, bi) => bi !== bulletIndex);
        next.bullets = bullets;
        return next;
      }),
    }));
    if (projectName) {
      dismissProjectBulletSuggestions(
        suggestions,
        onDismissSuggestion,
        projectName,
        [removedText],
      );
    }
  }

  async function addProjectBullet(projectIndex: number, text: string) {
    const entry = data.projects[projectIndex] as Record<string, unknown> | undefined;
    if (!entry) return;
    const newIdx = ((entry.bullets as string[]) ?? []).length;
    await patch({
      section: "projects",
      project_index: projectIndex,
      bullet_index: newIdx,
      new_text: text,
    });
    updateLocal((p) => ({
      ...p,
      projects: p.projects.map((proj, i) => {
        if (i !== projectIndex) return proj;
        const next = { ...(proj as Record<string, unknown>) };
        next.bullets = [...((next.bullets as string[]) ?? []), text];
        return next;
      }),
    }));
  }

  async function addProject(name: string, description: string, bullets: string[]) {
    const project = { name, description, bullets };
    await patch({ section: "projects", add_project: project });
    updateLocal((p) => ({
      ...p,
      projects: [...p.projects, project],
    }));
    dismissNewProjectSuggestions(suggestions, onDismissSuggestion, name);
  }

  async function deleteExpBullet(company: string, idx: number) {
    const entry = data.experience.find((e) => e.company === company);
    if (!entry) return;
    const removedText = entry.bullets[idx] ?? "";
    const bullets = entry.bullets.filter((_, i) => i !== idx);
    await patch({ section: "experience", company, bullet_index: idx, new_text: "" });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company ? { ...e, bullets } : e
      ),
    }));
    dismissExperienceBulletSuggestions(
      suggestions,
      onDismissSuggestion,
      company,
      [removedText],
    );
  }

  async function addExpBullet(company: string, text: string) {
    const entry = data.experience.find((e) => e.company === company);
    if (!entry) return;
    const newIdx = entry.bullets.length;
    await patch({ section: "experience", company, bullet_index: newIdx, new_text: text });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company ? { ...e, bullets: [...e.bullets, text] } : e
      ),
    }));
  }

  // ── Education bullets ────────────────────────────────────────────────────

  async function saveEduBullets(institution: string, bullets: string[]) {
    await patch({ section: "education_bullets", institution, bullets });
    updateLocal((p) => ({
      ...p,
      education: p.education.map((e) =>
        e.institution === institution ? { ...e, bullets } : e
      ),
    }));
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "education",
    );
  }

  async function saveEduBullet(institution: string, idx: number, text: string) {
    const entry = data.education.find((e) => e.institution === institution);
    if (!entry) return;
    const bullets = entry.bullets.map((b, i) => (i === idx ? text : b));
    await saveEduBullets(institution, bullets);
  }

  async function deleteEduBullet(institution: string, idx: number) {
    const entry = data.education.find((e) => e.institution === institution);
    if (!entry) return;
    const bullets = entry.bullets.filter((_, i) => i !== idx);
    await saveEduBullets(institution, bullets);
  }

  async function addEduBullet(institution: string, text: string) {
    const entry = data.education.find((e) => e.institution === institution);
    if (!entry) return;
    await saveEduBullets(institution, [...entry.bullets, text]);
  }

  async function saveEduField(
    institution: string,
    fields: { new_institution?: string; new_degree?: string; new_year?: string },
  ) {
    const hasChange =
      (fields.new_institution !== undefined && fields.new_institution.trim() !== institution) ||
      (fields.new_degree !== undefined && fields.new_degree.trim().length > 0) ||
      fields.new_year !== undefined;
    if (!hasChange) return;

    await patch({ section: "education", institution, ...fields });
    const newInstitution = fields.new_institution?.trim();
    updateLocal((p) => ({
      ...p,
      education: p.education.map((e) => {
        if (e.institution !== institution) return e;
        return {
          ...e,
          ...(newInstitution ? { institution: newInstitution } : {}),
          ...(fields.new_degree !== undefined ? { degree: fields.new_degree.trim() } : {}),
          ...(fields.new_year !== undefined ? { year: fields.new_year.trim() } : {}),
        };
      }),
    }));
    if (newInstitution) {
      setExpandedEdu(newInstitution);
    }
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "education",
    );
  }

  // ── Skills chip editor ───────────────────────────────────────────────────

  const [editingSkills, setEditingSkills] = useState(false);
  // Category lines need newline separator; plain skills use comma.
  const skillsHaveCategories = data.skills.some((s) => /^[A-Z][^:]+:\s*.+/.test(s));
  const [skillsDraft, setSkillsDraft] = useState(
    skillsHaveCategories ? data.skills.join("\n") : data.skills.join(", "),
  );
  const [skillsSaved, setSkillsSaved] = useState(false);

  async function commitSkills() {
    const raw = skillsDraft;
    // If any line contains ": " treat each line as an entry; else split on commas.
    const hasCategoryLines = raw.includes("\n") || /^[A-Z][^:]+:\s/.test(raw);
    const skills = hasCategoryLines
      ? raw.split("\n").map((s) => s.trim()).filter(Boolean)
      : raw.split(",").map((s) => s.trim()).filter(Boolean);
    await saveSkills(skills);
    setEditingSkills(false);
    setSkillsSaved(true);
    setTimeout(() => setSkillsSaved(false), 2000);
  }

  const pendingCount = pendingSuggestionCount(suggestions);

  return (
    <div className="space-y-8">
      <div className="rounded-xl border border-slate-700 bg-slate-800/40 px-4 py-3 text-xs text-slate-300">
        <p className="font-semibold text-slate-200 mb-1">Edit your resume directly — no chat required</p>
        <p>
          Use <strong>Edit</strong> or the pencil icon on summary, skills, experience, education, and projects.
          Expand an experience row to edit its bullets. Use the trash icon to remove a whole experience entry or project card.
        </p>
      </div>
      {pendingCount > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-xs text-amber-100 space-y-1.5">
          <div className="flex items-start justify-between gap-3">
            <p className="font-semibold text-amber-300">
              {pendingCount} pending suggestion{pendingCount !== 1 ? "s" : ""} — not applied yet
            </p>
            <div className="flex items-center gap-3 shrink-0">
              {(onAcceptAllSuggestions || onAcceptSuggestion) && (
                <button
                  type="button"
                  onClick={() => {
                    if (onAcceptAllSuggestions) {
                      onAcceptAllSuggestions();
                    } else {
                      for (const s of suggestions) {
                        if (s.status === "pending") onAcceptSuggestion?.(s.id);
                      }
                    }
                  }}
                  className="shrink-0 text-emerald-300 hover:text-emerald-100 underline text-[11px] font-semibold"
                >
                  Accept all
                </button>
              )}
              {onRejectSuggestion && (
                <button
                  type="button"
                  onClick={() => {
                    for (const s of suggestions) {
                      if (s.status === "pending") onRejectSuggestion(s.id);
                    }
                  }}
                  className="shrink-0 text-amber-300/80 hover:text-amber-200 underline text-[11px]"
                >
                  Ignore all
                </button>
              )}
            </div>
          </div>
          <p className="text-amber-200/80">
            <span className="inline-block w-2 h-2 rounded-sm bg-amber-500/60 mr-1 align-middle" />
            Yellow = proposed change
            <span className="mx-2">·</span>
            <span className="inline-block w-2 h-2 rounded-sm bg-emerald-500/60 mr-1 align-middle" />
            Green = accepted
            <span className="mx-2">·</span>
            Click <strong>Accept</strong> on each highlight to update your resume, or use <strong>Accept all</strong> above
          </p>
        </div>
      )}
      {suggestionDraft && (
        <div className="bg-amber-400/10 border border-amber-400/30 rounded-xl p-4 space-y-2">
          <p className="text-xs text-amber-400 font-semibold uppercase tracking-wide">
            ATS suggestion — edit and apply to your resume
          </p>
          <textarea
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            rows={3}
            className="w-full bg-slate-900 border border-amber-400/40 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
          />
          <button
            type="button"
            onClick={() => onClearSuggestion?.()}
            className="text-xs text-slate-400 hover:text-slate-200 underline"
          >
            Dismiss
          </button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleUndo}
            disabled={!canUndo}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30"
            title="Undo (Ctrl+Z)"
          >
            <Undo2 className="w-3.5 h-3.5" /> Undo
          </button>
          <button
            type="button"
            onClick={handleRedo}
            disabled={!canRedo}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30"
            title="Redo (Ctrl+Y)"
          >
            <Redo2 className="w-3.5 h-3.5" /> Redo
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAddMode(addMode ? null : "master")}
            className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 hover:bg-slate-700"
          >
            Add Section
          </button>
        </div>
      </div>

      {addMode && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setAddMode("master")}
              className={`px-3 py-1 rounded text-xs ${addMode === "master" ? "bg-amber-400 text-slate-900" : "bg-slate-700 text-slate-300"}`}
            >
              Pull from master resume
            </button>
            <button
              type="button"
              onClick={() => setAddMode("manual")}
              className={`px-3 py-1 rounded text-xs ${addMode === "manual" ? "bg-amber-400 text-slate-900" : "bg-slate-700 text-slate-300"}`}
            >
              Write manually
            </button>
          </div>

          {addMode === "master" && (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {skippedChunks.length === 0 ? (
                <p className="text-xs text-slate-500">No skipped master-resume chunks available.</p>
              ) : (
                skippedChunks.map((chunk) => (
                  <button
                    key={chunk.chunk_id}
                    type="button"
                    disabled={phaseRunning}
                    onClick={() => addFromMasterChunk(chunk)}
                    className="w-full text-left p-3 rounded-lg border border-slate-700 hover:border-amber-400/40 bg-slate-900/50 disabled:opacity-50"
                  >
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>{chunk.section}</span>
                      <span>score {chunk.score.toFixed(2)}</span>
                    </div>
                    <p className="text-sm text-slate-300 line-clamp-2">
                      {(chunk as { content?: string }).content ?? chunk.reason}
                    </p>
                  </button>
                ))
              )}
            </div>
          )}

          {addMode === "manual" && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ["experience", "Experience row"],
                    ["projects", "Project"],
                    ["certifications", "Certification / award"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setManualSectionType(value)}
                    className={`px-3 py-1 rounded text-xs ${
                      manualSectionType === value
                        ? "bg-amber-400 text-slate-900"
                        : "bg-slate-700 text-slate-300"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <input
                value={manualTitle}
                onChange={(e) => setManualTitle(e.target.value)}
                placeholder={
                  manualSectionType === "projects"
                    ? "Project name"
                    : manualSectionType === "certifications"
                      ? "Certification or award name"
                      : "Job title or section label (e.g. Awards)"
                }
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
              />
              {manualSectionType !== "certifications" && (
                <input
                  value={manualCompany}
                  onChange={(e) => setManualCompany(e.target.value)}
                  placeholder={
                    manualSectionType === "projects"
                      ? "One-line description (optional)"
                      : "Company / label"
                  }
                  className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
                />
              )}
              <textarea
                value={manualSectionText}
                onChange={(e) => setManualSectionText(e.target.value)}
                rows={4}
                placeholder={
                  manualSectionType === "certifications"
                    ? "Optional details (leave blank to use title only)"
                    : "Section content…"
                }
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm resize-none"
              />
              <button
                type="button"
                onClick={() => void saveManualSection()}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500"
              >
                Save section
              </button>
            </div>
          )}
        </div>
      )}

      {orphanedSuggestions(suggestions, data).length > 0 && (
        <section className="rounded-xl border border-red-500/40 bg-red-950/20 px-4 py-3">
          <SectionHeader
            title="Couldn't apply — chat suggestion didn't match your resume"
            count={orphanedSuggestions(suggestions, data).length}
          />
          <p className="text-xs text-red-200/80 mb-3">
            The AI proposed a change that doesn&apos;t match anything in your resume (maybe already deleted, wrong section, or wrong name).
            Click <strong>Ignore</strong> to dismiss, or edit manually with the pencil / trash icons.
          </p>
          <div className="space-y-2">
            {orphanedSuggestions(suggestions, data).map((sug) => (
              <OrphanSuggestionCard
                key={sug.id}
                suggestion={sug}
                onAccept={acceptSug}
                onReject={rejectSug}
              />
            ))}
          </div>
        </section>
      )}

      {/* ── Contact / name (appears on exported PDF) ─────────────────────── */}
      <section>
        <SectionHeader title="Name on resume" />
        <p className="text-xs text-slate-500 mb-2">
          This is the header on your downloaded PDF — edit here or ask chat to rename you.
        </p>
        {editingContactName ? (
          <span className="inline-flex items-center gap-2">
            <input
              value={editingContactValue}
              onChange={(e) => setEditingContactValue(e.target.value)}
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-lg font-semibold text-slate-100 min-w-[16rem]"
              autoFocus
            />
            <button
              type="button"
              onClick={() => {
                void saveContactName(editingContactValue);
                setEditingContactName(false);
              }}
              className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
            >
              <Check className="w-3 h-3" />
            </button>
            <button
              type="button"
              onClick={() => setEditingContactName(false)}
              className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ) : (
          <span className="inline-flex items-center gap-2">
            <span className="text-xl font-semibold text-slate-100">
              <InlineFieldSuggestion
                current={displayName || "Your name"}
                suggestion={contactNameSuggestion(suggestions)}
                label="name"
                onAccept={acceptSug}
                onReject={rejectSug}
              />
            </span>
            <button
              type="button"
              title="Edit name on resume"
              onClick={() => {
                setEditingContactValue(displayName);
                setEditingContactName(true);
              }}
              className="p-1 rounded text-slate-400 hover:text-amber-400 transition"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          </span>
        )}
      </section>

      {/* ── Summary ──────────────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <SectionHeader title="Professional Summary" />
          <button
            type="button"
            disabled={phaseRunning}
            onClick={() => regen({ section: "summary" })}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-400 disabled:opacity-40"
          >
            <RotateCw className="w-3.5 h-3.5" /> Regenerate
          </button>
        </div>
        <SummaryHighlight
          currentText={data.summary}
          suggestion={activeSummarySuggestion(suggestions)}
          onAccept={acceptSug}
          onReject={rejectSug}
        >
          <InlineText
            value={data.summary}
            onSave={saveSummary}
            rows={4}
            placeholder="2–3 sentences, max 60 words, include 3–4 exact JD keywords."
          />
        </SummaryHighlight>
      </section>

      {/* ── Skills ───────────────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <SectionHeader title="Skills" count={data.skills.length} />
          <div className="flex items-center gap-3">
            {!editingSkills && (
              <button
                type="button"
                onClick={() => {
                  const hasCats = data.skills.some((s) => /^[A-Z][^:]+:\s*.+/.test(s));
                  setSkillsDraft(hasCats ? data.skills.join("\n") : data.skills.join(", "));
                  setEditingSkills(true);
                }}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-400"
              >
                <Pencil className="w-3.5 h-3.5" /> Edit
              </button>
            )}
            <button
              type="button"
              disabled={phaseRunning}
              onClick={() => regen({ section: "skills" })}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-400 disabled:opacity-40"
            >
              <RotateCw className="w-3.5 h-3.5" /> Regenerate
            </button>
          </div>
        </div>
        {editingSkills ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">
              {skillsHaveCategories
                ? "One category per line — e.g. \"AI & ML: Python, LLMs, RAG\". Ordered by JD relevance."
                : "Comma-separated, ordered by JD relevance. Use \"Category: skill1, skill2\" format to group."}
            </p>
            <textarea
              autoFocus
              value={skillsDraft}
              onChange={(e) => setSkillsDraft(e.target.value)}
              rows={skillsHaveCategories ? 6 : 3}
              className="w-full bg-slate-900 border border-amber-400/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <div className="flex gap-2">
              <button
                onClick={commitSkills}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300"
              >
                <Save className="w-3 h-3" /> Save
              </button>
              <button
                onClick={() => {
                  const hasCats = data.skills.some((s) => /^[A-Z][^:]+:\s*.+/.test(s));
                  setSkillsDraft(hasCats ? data.skills.join("\n") : data.skills.join(", "));
                  setEditingSkills(false);
                }}
                className="px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="group relative space-y-2">
            {data.skills.map((s, i) => {
              const isCategoryLine = /^[A-Z][^:]+:\s*.+/.test(s);
              if (isCategoryLine) {
                const colonIdx = s.indexOf(": ");
                const category = s.slice(0, colonIdx);
                const items = s.slice(colonIdx + 2).split(",").map((x) => x.trim()).filter(Boolean);
                return (
                  <div key={i} className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{category}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {items.map((item, j) => (
                        <SkillChip
                          key={`${i}-${j}`}
                          skill={item}
                          tone={skillChipTone(item, suggestions, pendingSkillRemoves(suggestions), acceptedSkillAdds(suggestions))}
                          onAccept={acceptSug}
                          onReject={rejectSug}
                        />
                      ))}
                    </div>
                  </div>
                );
              }
              const removeSug = skillsSuggestions(suggestions).find(
                (sug) =>
                  sug.status === "pending" &&
                  (sug.patch.remove_skills ?? []).some((r) => r.toLowerCase() === s.toLowerCase()),
              );
              return (
                <SkillChip
                  key={i}
                  skill={s}
                  tone={skillChipTone(s, suggestions, pendingSkillRemoves(suggestions), acceptedSkillAdds(suggestions))}
                  suggestion={removeSug}
                  onAccept={acceptSug}
                  onReject={rejectSug}
                />
              );
            })}
            {pendingSkillAdds(suggestions).map((s) => (
              <SkillChip
                key={`add-${s}`}
                skill={s}
                tone="pending"
                onAccept={acceptSug}
                onReject={rejectSug}
              />
            ))}
            {skillsSuggestions(suggestions)
              .filter((sug) => sug.status === "pending" && (sug.patch.add_skills?.length ?? 0) > 0)
              .map((sug) => (
                <div key={sug.id} className="flex justify-end mt-2">
                  <SuggestionActionButtons
                    onAccept={() => acceptSug(sug.id)}
                    onReject={() => rejectSug(sug.id)}
                  />
                </div>
              ))}
            {skillsSaved && <div className="mt-1"><SavedBadge /></div>}
          </div>
        )}
      </section>

      {/* ── Experience ───────────────────────────────────────────────────── */}
      {data.experience.length > 0 && (
        <section>
          <SectionHeader title="Experience" count={data.experience.length} />
          <div className="space-y-3">
            {data.experience.map((exp, expIndex) => {
              const open = expandedExp === exp.company;
              const deleteSug = experienceDeleteSuggestion(suggestions, exp.company);
              const hasPendingHighlight =
                experienceSuggestions(suggestions, exp.company).some((s) => s.status === "pending");
              const deleteTone = deleteSug?.status === "pending" ? "pending" : "none";
              return (
                <div
                  key={`exp-${expIndex}-${exp.company}`}
                  id={resumeAnchorDomId({ section: "experience", entry_index: expIndex })}
                  className={`border rounded-xl overflow-hidden ${
                    deleteTone === "pending"
                      ? "border-red-500/50 bg-red-950/20"
                      : hasPendingHighlight
                      ? "border-amber-500/50 ring-1 ring-amber-500/25"
                      : "border-slate-700"
                  }`}
                >
                  <button
                    onClick={() => setExpandedExp(open ? null : exp.company)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-800 text-left transition"
                  >
                    <div>
                      <p className="text-slate-100 text-sm font-semibold">
                        {editingExpField === `${exp.company}:title` ? (
                          <span
                            className="inline-flex items-center gap-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              autoFocus
                              value={editingExpValue}
                              onChange={(e) => setEditingExpValue(e.target.value)}
                              onKeyDown={async (e) => {
                                if (e.key === "Enter") {
                                  await saveExpTitle(exp.company, editingExpValue);
                                  setEditingExpField(null);
                                }
                                if (e.key === "Escape") setEditingExpField(null);
                              }}
                              className="bg-slate-700 border border-amber-400/60 rounded px-2 py-0.5 text-sm text-slate-100 outline-none w-72"
                            />
                            <button
                              type="button"
                              onClick={async () => {
                                await saveExpTitle(exp.company, editingExpValue);
                                setEditingExpField(null);
                              }}
                              className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                            >
                              <Check className="w-3 h-3" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingExpField(null)}
                              className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 group/title">
                            <InlineFieldSuggestion
                              current={exp.title}
                              suggestion={titleSuggestion(suggestions, exp.company)}
                              label="title"
                              onAccept={acceptSug}
                              onReject={rejectSug}
                            />
                            <button
                              type="button"
                              title="Edit title"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingExpField(`${exp.company}:title`);
                                setEditingExpValue(exp.title);
                              }}
                              className="p-0.5 rounded text-slate-400 hover:text-amber-400 transition opacity-80"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                          </span>
                        )}
                      </p>
                      <p className="text-slate-400 text-xs">
                        {editingExpField === `${exp.company}:company` ? (
                          <span
                            className="inline-flex items-center gap-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              autoFocus
                              value={editingExpValue}
                              onChange={(e) => setEditingExpValue(e.target.value)}
                              onKeyDown={async (e) => {
                                if (e.key === "Enter") {
                                  await saveExpCompany(exp.company, editingExpValue);
                                  setEditingExpField(null);
                                  setExpandedExp(editingExpValue.trim() || exp.company);
                                }
                                if (e.key === "Escape") setEditingExpField(null);
                              }}
                              className="bg-slate-700 border border-amber-400/60 rounded px-2 py-0.5 text-xs text-slate-200 outline-none w-56"
                            />
                            <button
                              type="button"
                              onClick={async () => {
                                await saveExpCompany(exp.company, editingExpValue);
                                setExpandedExp(editingExpValue.trim() || exp.company);
                                setEditingExpField(null);
                              }}
                              className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                            >
                              <Check className="w-3 h-3" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingExpField(null)}
                              className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 group/company">
                            {exp.company}
                            <button
                              type="button"
                              title="Edit company name"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingExpField(`${exp.company}:company`);
                                setEditingExpValue(exp.company);
                              }}
                              className="p-0.5 rounded text-slate-400 hover:text-amber-400 transition opacity-80"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                          </span>
                        )}
                        {" "}·{" "}
                        {editingExpField === `${exp.company}:dates` ? (
                          <span
                            className="inline-flex items-center gap-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              autoFocus
                              value={editingExpValue}
                              onChange={(e) => setEditingExpValue(e.target.value)}
                              onKeyDown={async (e) => {
                                if (e.key === "Enter") {
                                  await saveExpDates(exp.company, editingExpValue);
                                  setEditingExpField(null);
                                }
                                if (e.key === "Escape") setEditingExpField(null);
                              }}
                              className="bg-slate-700 border border-amber-400/60 rounded px-2 py-0.5 text-xs text-slate-200 outline-none w-36"
                            />
                            <button
                              type="button"
                              onClick={async () => {
                                await saveExpDates(exp.company, editingExpValue);
                                setEditingExpField(null);
                              }}
                              className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                            >
                              <Check className="w-3 h-3" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingExpField(null)}
                              className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1">
                            <InlineFieldSuggestion
                              current={exp.dates}
                              suggestion={datesSuggestion(suggestions, exp.company)}
                              label="dates"
                              onAccept={acceptSug}
                              onReject={rejectSug}
                            />
                            <button
                              type="button"
                              title="Edit dates"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingExpField(`${exp.company}:dates`);
                                setEditingExpValue(exp.dates);
                              }}
                              className="p-0.5 rounded text-slate-400 hover:text-amber-400 transition opacity-80"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {entryIssueBadges[entryAnchorKey("experience", expIndex)] && (
                        <EntryIssueBadgePill
                          badge={entryIssueBadges[entryAnchorKey("experience", expIndex)]!}
                        />
                      )}
                      {exp.keywords_injected?.length > 0 && (
                        <span className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded px-1.5 py-0.5">
                          {exp.keywords_injected.length} kw injected
                        </span>
                      )}
                      <button
                        type="button"
                        title="Delete this entry (e.g. manual Awards section)"
                        onClick={(e) => {
                          e.stopPropagation();
                          void deleteExperienceEntry(expIndex);
                        }}
                        className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-950/30 transition"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      {open ? (
                        <ChevronUp className="w-4 h-4 text-slate-500" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-slate-500" />
                      )}
                    </div>
                  </button>

                  {open && (
                    <div className="px-4 py-4 space-y-4 bg-slate-900/40">
                      <div className="flex justify-end">
                        <button
                          type="button"
                          disabled={phaseRunning}
                          onClick={() => regen({ section: "experience", company: exp.company })}
                          className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-400 disabled:opacity-40"
                        >
                          <RotateCw className="w-3.5 h-3.5" /> Regenerate section
                        </button>
                      </div>
                      <ScopedBulletList
                        bullets={exp.bullets}
                        company={exp.company}
                        phaseRunning={phaseRunning}
                        suggestions={suggestions}
                        onAcceptSuggestion={acceptSug}
                        onRejectSuggestion={rejectSug}
                        onRegenBullet={(idx) =>
                          regen({ section: "experience", company: exp.company, bullet_index: idx })
                        }
                        onSaveBullet={(idx, text) => saveExpBullet(exp.company, idx, text)}
                        onDeleteBullet={(idx) => deleteExpBullet(exp.company, idx)}
                        onAddBullet={(text) => addExpBullet(exp.company, text)}
                        addPlaceholder="Strong action verb + metric + JD keyword…"
                      />

                      {exp.removed_bullets?.length > 0 && (
                        <div>
                          <p className="text-xs text-slate-500 font-semibold mb-1.5">Removed (not JD-relevant)</p>
                          <div className="space-y-1">
                            {exp.removed_bullets.map((rb, i) => (
                              <p key={i} className="text-slate-600 text-xs line-through pl-4">{rb}</p>
                            ))}
                          </div>
                        </div>
                      )}
                      {deleteSug?.status === "pending" && (
                        <div className="flex items-center justify-between pt-2 border-t border-red-500/30">
                          <p className="text-red-300 text-xs">Suggested removal of this experience entry</p>
                          <SuggestionActionButtons
                            onAccept={() => acceptSug(deleteSug.id)}
                            onReject={() => rejectSug(deleteSug.id)}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Education ────────────────────────────────────────────────────── */}
      {data.education.length > 0 && (
        <section>
          <SectionHeader title="Education" count={data.education.length} />
          <p className="text-[11px] text-slate-500 mb-3 -mt-2">
            Click a row to expand bullets · use the pencil to edit degree, school, or year
          </p>
          <div className="space-y-3">
            {data.education.map((edu, eduIndex) => {
              const open = expandedEdu === edu.institution;
              const renameSug = institutionRenameSuggestion(
                suggestions,
                edu.institution,
                data.education,
              );
              const bulletAddSugs = educationBulletAddSuggestions(
                suggestions,
                edu.institution,
                data.education,
              );
              const eduPending = hasPendingEducationSuggestions(
                suggestions,
                edu.institution,
                data.education,
              );
              const fieldKey = (field: "degree" | "institution" | "year") =>
                `${edu.institution}:${field}`;

              return (
                <div
                  key={edu.institution}
                  id={resumeAnchorDomId({ section: "education", entry_index: eduIndex })}
                  className={`border rounded-xl overflow-hidden ${
                    eduPending
                      ? "border-amber-500/50 ring-1 ring-amber-500/25"
                      : "border-slate-700"
                  }`}
                >
                  <button
                    onClick={() => setExpandedEdu(open ? null : edu.institution)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-800 text-left transition"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <GraduationCap className="w-4 h-4 text-slate-400 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-slate-100 text-sm font-semibold">
                          {editingEduField === fieldKey("degree") ? (
                            <span
                              className="inline-flex items-center gap-1"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                autoFocus
                                value={editingEduValue}
                                onChange={(e) => setEditingEduValue(e.target.value)}
                                onKeyDown={async (e) => {
                                  if (e.key === "Enter") {
                                    await saveEduField(edu.institution, { new_degree: editingEduValue });
                                    setEditingEduField(null);
                                  }
                                  if (e.key === "Escape") setEditingEduField(null);
                                }}
                                className="bg-slate-700 border border-amber-400/60 rounded px-2 py-0.5 text-sm text-slate-100 outline-none w-64 max-w-full"
                              />
                              <button
                                type="button"
                                onClick={async () => {
                                  await saveEduField(edu.institution, { new_degree: editingEduValue });
                                  setEditingEduField(null);
                                }}
                                className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                              >
                                <Check className="w-3 h-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingEduField(null)}
                                className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              {edu.degree}
                              <button
                                type="button"
                                title="Edit degree"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingEduField(fieldKey("degree"));
                                  setEditingEduValue(edu.degree);
                                }}
                                className="p-0.5 rounded text-slate-400 hover:text-amber-400 opacity-80"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            </span>
                          )}
                        </p>
                        <p className="text-slate-400 text-xs flex flex-wrap items-center gap-x-1">
                          {editingEduField === fieldKey("institution") ? (
                            <span
                              className="inline-flex items-center gap-1"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                autoFocus
                                value={editingEduValue}
                                onChange={(e) => setEditingEduValue(e.target.value)}
                                onKeyDown={async (e) => {
                                  if (e.key === "Enter") {
                                    await saveEduField(edu.institution, {
                                      new_institution: editingEduValue,
                                    });
                                    setEditingEduField(null);
                                  }
                                  if (e.key === "Escape") setEditingEduField(null);
                                }}
                                className="bg-slate-700 border border-amber-400/60 rounded px-2 py-0.5 text-xs text-slate-200 outline-none w-48 max-w-full"
                              />
                              <button
                                type="button"
                                onClick={async () => {
                                  await saveEduField(edu.institution, {
                                    new_institution: editingEduValue,
                                  });
                                  setEditingEduField(null);
                                }}
                                className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                              >
                                <Check className="w-3 h-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingEduField(null)}
                                className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              <InlineFieldSuggestion
                                current={edu.institution}
                                suggestion={renameSug}
                                label="institution"
                                onAccept={acceptSug}
                                onReject={rejectSug}
                              />
                              <button
                                type="button"
                                title="Edit institution"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingEduField(fieldKey("institution"));
                                  setEditingEduValue(edu.institution);
                                }}
                                className="p-0.5 rounded text-slate-400 hover:text-amber-400 opacity-80"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            </span>
                          )}
                          <span>·</span>
                          {editingEduField === fieldKey("year") ? (
                            <span
                              className="inline-flex items-center gap-1"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                autoFocus
                                value={editingEduValue}
                                onChange={(e) => setEditingEduValue(e.target.value)}
                                onKeyDown={async (e) => {
                                  if (e.key === "Enter") {
                                    await saveEduField(edu.institution, { new_year: editingEduValue });
                                    setEditingEduField(null);
                                  }
                                  if (e.key === "Escape") setEditingEduField(null);
                                }}
                                placeholder="Year"
                                className="bg-slate-700 border border-amber-400/60 rounded px-2 py-0.5 text-xs text-slate-200 outline-none w-24"
                              />
                              <button
                                type="button"
                                onClick={async () => {
                                  await saveEduField(edu.institution, { new_year: editingEduValue });
                                  setEditingEduField(null);
                                }}
                                className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                              >
                                <Check className="w-3 h-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingEduField(null)}
                                className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              {edu.year || (
                                <span className="text-slate-600 italic">no year</span>
                              )}
                              <button
                                type="button"
                                title="Edit year"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingEduField(fieldKey("year"));
                                  setEditingEduValue(edu.year);
                                }}
                                className="p-0.5 rounded text-slate-400 hover:text-amber-400 opacity-80"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            </span>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {entryIssueBadges[entryAnchorKey("education", eduIndex)] && (
                        <EntryIssueBadgePill
                          badge={entryIssueBadges[entryAnchorKey("education", eduIndex)]!}
                        />
                      )}
                      {edu.bullets.length > 0 && (
                        <span className="text-xs text-slate-500">
                          {edu.bullets.length} bullet{edu.bullets.length !== 1 ? "s" : ""}
                        </span>
                      )}
                      {open ? (
                        <ChevronUp className="w-4 h-4 text-slate-500" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-slate-500" />
                      )}
                    </div>
                  </button>

                  {open && (
                    <div className="px-4 py-4 bg-slate-900/40 space-y-4">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="text-xs text-slate-500 mb-1.5">Degree</p>
                          <InlineText
                            value={edu.degree}
                            onSave={(text) => saveEduField(edu.institution, { new_degree: text })}
                            rows={1}
                            placeholder="Degree or program name"
                          />
                        </div>
                        <div>
                          <p className="text-xs text-slate-500 mb-1.5">Institution</p>
                          <InlineText
                            value={edu.institution}
                            onSave={(text) =>
                              saveEduField(edu.institution, { new_institution: text })
                            }
                            rows={1}
                            placeholder="School or program name"
                          />
                        </div>
                        <div>
                          <p className="text-xs text-slate-500 mb-1.5">Year</p>
                          <InlineText
                            value={edu.year}
                            onSave={(text) => saveEduField(edu.institution, { new_year: text })}
                            rows={1}
                            placeholder="e.g. 2024"
                          />
                        </div>
                      </div>
                      {edu.bullets.length === 0 && bulletAddSugs.length === 0 && (
                        <p className="text-slate-600 text-xs flex items-center gap-1.5">
                          <Info className="w-3.5 h-3.5" />
                          No bullets yet — add relevant coursework, GPA, thesis, or activities.
                        </p>
                      )}
                      <BulletList
                        bullets={edu.bullets}
                        onSaveBullet={(idx, text) => saveEduBullet(edu.institution, idx, text)}
                        onDeleteBullet={(idx) => deleteEduBullet(edu.institution, idx)}
                        onAddBullet={(text) => addEduBullet(edu.institution, text)}
                        addPlaceholder="e.g. Relevant coursework: Machine Learning · GPA: 3.9/4.0"
                      />
                      {bulletAddSugs.map((sug) => (
                        <PendingAdditionCard
                          key={sug.id}
                          suggestion={sug}
                          onAccept={acceptSug}
                          onReject={rejectSug}
                        >
                          <div className="space-y-1">
                            {(sug.patch.add_education_bullets ?? []).map((bullet, bi) => (
                              <p key={bi} className="text-amber-100 text-sm flex gap-2">
                                <span className="text-amber-400 shrink-0">+</span>
                                {bullet}
                              </p>
                            ))}
                          </div>
                        </PendingAdditionCard>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Projects ─────────────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <SectionHeader title="Projects" count={data.projects.length} />
          <button
            type="button"
            onClick={() => setAddingProject((v) => !v)}
            className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"
          >
            <Plus className="w-3.5 h-3.5" /> Add project
          </button>
        </div>

        {addingProject && (
          <div className="mb-4 border border-emerald-500/30 rounded-xl p-4 bg-emerald-950/10 space-y-2">
            <input
              autoFocus
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Project name"
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200"
            />
            <input
              value={newProjectDesc}
              onChange={(e) => setNewProjectDesc(e.target.value)}
              placeholder="One-line description (optional)"
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200"
            />
            <textarea
              value={newProjectBullets}
              onChange={(e) => setNewProjectBullets(e.target.value)}
              placeholder="One bullet per line…"
              rows={4}
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 resize-none"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={async () => {
                  const bullets = newProjectBullets
                    .split("\n")
                    .map((b) => b.trim())
                    .filter(Boolean);
                  if (!newProjectName.trim()) return;
                  await addProject(newProjectName.trim(), newProjectDesc.trim(), bullets);
                  setNewProjectName("");
                  setNewProjectDesc("");
                  setNewProjectBullets("");
                  setAddingProject(false);
                }}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500"
              >
                Save project
              </button>
              <button
                type="button"
                onClick={() => setAddingProject(false)}
                className="px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {data.projects.length > 0 && (
          <div className="space-y-3">
            {data.projects.map((proj, i) => {
              const p = proj as Record<string, unknown>;
              const projectName = String(p.name ?? "");
              const projectDesc = String(p.description ?? "");
              const bullets = (p.bullets as string[]) ?? [];
              const removalSug = projectRemovalPending(suggestions, projectName);
              const replaceAllSug = projectReplaceAllSuggestion(suggestions, projectName);
              const titleSug = projectTitleSuggestion(suggestions, projectName);
              const descSug = projectDescriptionSuggestion(suggestions, projectName);
              const removalTone = removalSug?.status === "accepted"
                ? "accepted"
                : removalSug?.status === "pending"
                  ? "pending"
                  : "none";

              return (
                <div
                  key={`project-${i}-${projectName}`}
                  id={resumeAnchorDomId({ section: "projects", entry_index: i })}
                  className={`border rounded-xl px-4 py-3 ${
                    removalTone === "pending"
                      ? "border-red-500/50 bg-red-950/20"
                      : removalTone === "accepted"
                        ? "border-emerald-500/40 bg-emerald-950/10 opacity-60"
                        : "border-slate-700 bg-slate-800/30"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex-1 min-w-0 space-y-1">
                      {editingProjectField === `${i}:name` ? (
                        <div className="flex items-center gap-1">
                          <input
                            autoFocus
                            value={editingProjectValue}
                            onChange={(e) => setEditingProjectValue(e.target.value)}
                            className="flex-1 bg-slate-900 border border-amber-400/60 rounded px-2 py-1 text-sm text-slate-100 outline-none"
                          />
                          <button
                            type="button"
                            onClick={async () => {
                              await saveProjectMeta(i, { new_name: editingProjectValue });
                              setEditingProjectField(null);
                            }}
                            className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                          >
                            <Check className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingProjectField(null)}
                            className="p-1 rounded bg-slate-600 hover:bg-slate-500 text-slate-300"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <p className={`text-sm font-semibold flex items-center gap-1 flex-wrap ${
                          removalTone === "pending" ? "text-red-300 line-through" : "text-slate-100"
                        }`}>
                          <InlineFieldSuggestion
                            current={projectName}
                            suggestion={titleSug}
                            label="project_title"
                            onAccept={acceptSug}
                            onReject={rejectSug}
                          />
                          {!titleSug && (
                            <button
                              type="button"
                              title="Edit project name"
                              onClick={() => {
                                setEditingProjectField(`${i}:name`);
                                setEditingProjectValue(projectName);
                              }}
                              className="p-0.5 rounded text-slate-400 hover:text-amber-400 opacity-80"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                          )}
                        </p>
                      )}
                      {(projectDesc || editingProjectField === `${i}:description`) && (
                        editingProjectField === `${i}:description` ? (
                          <div className="flex items-center gap-1">
                            <input
                              autoFocus
                              value={editingProjectValue}
                              onChange={(e) => setEditingProjectValue(e.target.value)}
                              className="flex-1 bg-slate-900 border border-amber-400/60 rounded px-2 py-1 text-xs text-slate-200 outline-none"
                            />
                            <button
                              type="button"
                              onClick={async () => {
                                await saveProjectMeta(i, { new_description: editingProjectValue });
                                setEditingProjectField(null);
                              }}
                              className="p-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                            >
                              <Check className="w-3 h-3" />
                            </button>
                          </div>
                        ) : (
                          <p className="text-slate-400 text-xs flex items-center gap-1 flex-wrap">
                            <InlineFieldSuggestion
                              current={projectDesc}
                              suggestion={descSug}
                              label="project_description"
                              onAccept={acceptSug}
                              onReject={rejectSug}
                            />
                            {!descSug && (
                              <button
                                type="button"
                                title="Edit description"
                                onClick={() => {
                                  setEditingProjectField(`${i}:description`);
                                  setEditingProjectValue(projectDesc);
                                }}
                                className="p-0.5 rounded text-slate-400 hover:text-amber-400 opacity-80"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            )}
                          </p>
                        )
                      )}
                      {!projectDesc && editingProjectField !== `${i}:description` && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingProjectField(`${i}:description`);
                            setEditingProjectValue("");
                          }}
                          className="text-[10px] text-slate-500 hover:text-amber-400"
                        >
                          + Add description
                        </button>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {entryIssueBadges[entryAnchorKey("projects", i)] && (
                        <EntryIssueBadgePill
                          badge={entryIssueBadges[entryAnchorKey("projects", i)]!}
                        />
                      )}
                      {!!p.url && (
                        <a
                          href={String(p.url)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-slate-500 hover:text-amber-400 truncate max-w-[120px]"
                        >
                          {String(p.url)}
                        </a>
                      )}
                      <button
                        type="button"
                        title="Delete this project"
                        onClick={() => void deleteProject(i)}
                        className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-950/30 transition"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {replaceAllSug?.status === "pending" ? (
                    <PendingAdditionCard
                      suggestion={replaceAllSug}
                      onAccept={acceptSug}
                      onReject={rejectSug}
                    >
                      <div className="space-y-1">
                        {bullets.map((b, j) => (
                          <p key={j} className="text-red-300/70 text-sm line-through flex gap-2">
                            <span className="shrink-0">•</span>{b}
                          </p>
                        ))}
                        {(replaceAllSug.patch.project_bullets_replace_all ?? []).map((b, j) => (
                          <p key={`new-${j}`} className="text-amber-100 text-sm flex gap-2">
                            <span className="text-amber-400 shrink-0">•</span>{b}
                          </p>
                        ))}
                      </div>
                    </PendingAdditionCard>
                  ) : (
                    <BulletList
                      bullets={bullets}
                      onSaveBullet={(idx, text) => saveProjectBullet(i, idx, text)}
                      onDeleteBullet={(idx) => deleteProjectBullet(i, idx)}
                      onAddBullet={(text) => addProjectBullet(i, text)}
                      addPlaceholder="Action + metric + tech…"
                    />
                  )}

                  {removalSug?.status === "pending" && (
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-red-500/30">
                      <p className="text-red-300 text-xs">Suggested removal</p>
                      <SuggestionActionButtons
                        onAccept={() => acceptSug(removalSug.id)}
                        onReject={() => rejectSug(removalSug.id)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {newProjectSuggestions(suggestions, data).map((sug) => (
          <PendingAdditionCard
            key={sug.id}
            suggestion={sug}
            onAccept={acceptSug}
            onReject={rejectSug}
          >
            <p className="text-amber-200 text-sm font-semibold">{sug.patch.new_project?.name}</p>
            {sug.patch.new_project?.description && (
              <p className="text-amber-200/60 text-xs mt-0.5">{sug.patch.new_project.description}</p>
            )}
            {(sug.patch.new_project?.bullets ?? []).map((b, j) => (
              <p key={j} className="text-amber-100/90 text-sm flex gap-2 mt-1">
                <span className="text-amber-400 shrink-0">•</span>{b}
              </p>
            ))}
          </PendingAdditionCard>
        ))}
      </section>

      {/* ── Certifications ───────────────────────────────────────────────── */}
      {data.certifications.length > 0 && (
        <section>
          <SectionHeader title="Certifications & Awards" count={data.certifications.length} />
          <div className="flex flex-wrap gap-1.5">
            {data.certifications.map((c, i) => (
              <span
                key={i}
                className="group inline-flex items-center gap-1 bg-slate-800 border border-slate-700 text-slate-300 rounded px-2.5 py-1 text-xs"
              >
                {c}
                <button
                  type="button"
                  title="Remove"
                  onClick={() => void deleteCertification(i)}
                  className="p-0.5 rounded text-slate-500 hover:text-red-400 opacity-80"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        </section>
      )}

      {/* ── Metrics needed ───────────────────────────────────────────────── */}
      {data.metrics_needed.length > 0 && (
        <section>
          <SectionHeader title="Metrics Needed" count={data.metrics_needed.length} />
          <p className="text-slate-500 text-xs mb-3">
            The AI couldn't fabricate these numbers. Add them to your resume and re-run the rewrite.
          </p>
          <div className="space-y-2">
            {data.metrics_needed.map((m, i) => (
              <div
                key={i}
                className="flex items-start gap-2 bg-amber-400/5 border border-amber-400/20 rounded-lg px-3 py-2.5 text-sm"
              >
                <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-amber-300 text-xs font-medium mb-0.5">
                    {m.section}
                    {m.company ? ` · ${m.company}` : ""} · bullet {m.bullet_index + 1}
                  </p>
                  <p className="text-slate-300">{m.prompt}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Rewrite notes ────────────────────────────────────────────────── */}
      {data.rewrite_notes.length > 0 && (
        <section>
          <button
            onClick={() => setShowNotes((v) => !v)}
            className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 transition mb-2"
          >
            {showNotes ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showNotes ? "Hide" : "Show"} AI rewrite notes ({data.rewrite_notes.length})
          </button>
          {showNotes && (
            <div className="space-y-1.5">
              {data.rewrite_notes.map((note, i) => (
                <p key={i} className="text-slate-500 text-xs flex gap-2">
                  <span className="text-slate-700 shrink-0">·</span>
                  {note}
                </p>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
