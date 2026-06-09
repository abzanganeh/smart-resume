"use client";

import { useEffect, useState } from "react";
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
} from "lucide-react";
import {
  patchTailoredResume,
  saveTailoredResume,
  type PhaseRunScope,
  type TailoredResumeOutput,
} from "@/lib/api";
import { useVersionStack } from "@/lib/useVersionStack";
import type { ResumeSuggestion } from "@/lib/suggestions";
import {
  acceptedBulletSuggestion,
  acceptedProjectBulletSuggestion,
  acceptedSkillAdds,
  activeSummarySuggestion,
  bulletEditSuggestion,
  datesSuggestion,
  educationBulletAddSuggestions,
  educationSuggestions,
  hasPendingEducationSuggestions,
  experienceSuggestions,
  institutionRenameSuggestion,
  newProjectSuggestions,
  orphanedSuggestions,
  pendingSkillAdds,
  pendingSkillRemoves,
  pendingSuggestionCount,
  projectBulletEditSuggestion,
  projectRemovalPending,
  projectReplaceAllSuggestion,
  skillChipTone,
  skillsSuggestions,
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

interface Props {
  initial: TailoredResumeOutput;
  sessionId: string;
  onSaved?: (updated: TailoredResumeOutput) => void;
  onScopedRun?: (scope: PhaseRunScope) => void;
  phaseRunning?: boolean;
  suggestionDraft?: string | null;
  onClearSuggestion?: () => void;
  suggestions?: ResumeSuggestion[];
  onAcceptSuggestion?: (id: string) => void;
  onRejectSuggestion?: (id: string) => void;
  onDismissSuggestion?: (id: string) => void;
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
          className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 p-1 rounded text-slate-500 hover:text-amber-400 transition"
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
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition shrink-0">
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

export function TailoredEditor({ initial, sessionId, onSaved, onScopedRun, phaseRunning, suggestionDraft, onClearSuggestion, suggestions = [], onAcceptSuggestion, onRejectSuggestion, onDismissSuggestion }: Props) {
  function acceptSug(id: string) { onAcceptSuggestion?.(id); }
  function rejectSug(id: string) { onRejectSuggestion?.(id); }

  const { present: data, push, replace, undo, redo, canUndo, canRedo } = useVersionStack(initial);
  const [draftText, setDraftText] = useState(suggestionDraft ?? "");

  useEffect(() => {
    if (suggestionDraft) setDraftText(suggestionDraft);
  }, [suggestionDraft]);
  const [expandedExp, setExpandedExp] = useState<string | null>(
    initial.experience[0]?.company ?? null
  );
  const [expandedEdu, setExpandedEdu] = useState<string | null>(null);
  const [showNotes, setShowNotes] = useState(false);
  const [addMode, setAddMode] = useState<"master" | "manual" | null>(null);
  const [manualSectionText, setManualSectionText] = useState("");
  const [manualTitle, setManualTitle] = useState("Experience");
  const [manualCompany, setManualCompany] = useState("Manual entry");

  useEffect(() => {
    replace(initial);
  }, [initial, replace]);

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
    if (!manualSectionText.trim()) return;
    await patch({
      section_id: "add_section",
      content: {
        section: "experience",
        title: manualTitle,
        company: manualCompany,
        text: manualSectionText.trim(),
      },
    });
    updateLocal((p) => ({
      ...p,
      experience: [
        ...p.experience,
        {
          title: manualTitle,
          company: manualCompany,
          dates: "",
          bullets: [manualSectionText.trim()],
          removed_bullets: [],
          keywords_injected: [],
        },
      ],
    }));
    setManualSectionText("");
    setAddMode(null);
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
    await patch({ section: "experience", company, bullet_index: idx, new_text: text });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company
          ? { ...e, bullets: e.bullets.map((b, i) => (i === idx ? text : b)) }
          : e
      ),
    }));
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "experience",
    );
  }

  async function deleteExpBullet(company: string, idx: number) {
    const entry = data.experience.find((e) => e.company === company);
    if (!entry) return;
    const bullets = entry.bullets.filter((_, i) => i !== idx);
    await patch({ section: "experience", company, bullet_index: idx, new_text: "" });
    updateLocal((p) => ({
      ...p,
      experience: p.experience.map((e) =>
        e.company === company ? { ...e, bullets } : e
      ),
    }));
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

  async function saveEduInstitution(oldInstitution: string, newInstitution: string) {
    const trimmed = newInstitution.trim();
    if (!trimmed || trimmed === oldInstitution.trim()) return;
    const nextEducation = data.education.map((e) =>
      e.institution === oldInstitution ? { ...e, institution: trimmed } : e,
    );
    const next = { ...data, education: nextEducation };
    updateLocal(() => next);
    await saveTailoredResume(sessionId, next);
    dismissAcceptedForSection(
      suggestions,
      onDismissSuggestion,
      (s) => s.patch.section === "education",
    );
  }

  // ── Skills chip editor ───────────────────────────────────────────────────

  const [editingSkills, setEditingSkills] = useState(false);
  const [skillsDraft, setSkillsDraft] = useState(data.skills.join(", "));
  const [skillsSaved, setSkillsSaved] = useState(false);

  async function commitSkills() {
    const skills = skillsDraft
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await saveSkills(skills);
    setEditingSkills(false);
    setSkillsSaved(true);
    setTimeout(() => setSkillsSaved(false), 2000);
  }

  const pendingCount = pendingSuggestionCount(suggestions);

  return (
    <div className="space-y-8">
      {pendingCount > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-xs text-amber-100 space-y-1.5">
          <p className="font-semibold text-amber-300">
            {pendingCount} pending suggestion{pendingCount !== 1 ? "s" : ""} — not applied yet
          </p>
          <p className="text-amber-200/80">
            <span className="inline-block w-2 h-2 rounded-sm bg-amber-500/60 mr-1 align-middle" />
            Yellow = proposed change
            <span className="mx-2">·</span>
            <span className="inline-block w-2 h-2 rounded-sm bg-emerald-500/60 mr-1 align-middle" />
            Green = accepted
            <span className="mx-2">·</span>
            Click <strong>Accept</strong> on each highlight to update your resume
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
            onClick={undo}
            disabled={!canUndo}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30"
            title="Undo (Ctrl+Z)"
          >
            <Undo2 className="w-3.5 h-3.5" /> Undo
          </button>
          <button
            type="button"
            onClick={redo}
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
              <input
                value={manualTitle}
                onChange={(e) => setManualTitle(e.target.value)}
                placeholder="Title"
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
              />
              <input
                value={manualCompany}
                onChange={(e) => setManualCompany(e.target.value)}
                placeholder="Company / label"
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm"
              />
              <textarea
                value={manualSectionText}
                onChange={(e) => setManualSectionText(e.target.value)}
                rows={4}
                placeholder="Section content…"
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm resize-none"
              />
              <button
                type="button"
                onClick={saveManualSection}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500"
              >
                Save section
              </button>
            </div>
          )}
        </div>
      )}

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
          <button
            type="button"
            disabled={phaseRunning}
            onClick={() => regen({ section: "skills" })}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-400 disabled:opacity-40"
          >
            <RotateCw className="w-3.5 h-3.5" /> Regenerate
          </button>
        </div>
        {editingSkills ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">Comma-separated, ordered by JD relevance.</p>
            <textarea
              autoFocus
              value={skillsDraft}
              onChange={(e) => setSkillsDraft(e.target.value)}
              rows={3}
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
                onClick={() => { setSkillsDraft(data.skills.join(", ")); setEditingSkills(false); }}
                className="px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="group relative">
            <div className="flex flex-wrap gap-1.5 pr-8">
              {data.skills.map((s, i) => {
                const removeSug = skillsSuggestions(suggestions).find(
                  (sug) =>
                    sug.status === "pending" &&
                    (sug.patch.remove_skills ?? []).some((r) => r.toLowerCase() === s.toLowerCase()),
                );
                return (
                  <SkillChip
                    key={i}
                    skill={s}
                    tone={skillChipTone(
                      s,
                      suggestions,
                      pendingSkillRemoves(suggestions),
                      acceptedSkillAdds(suggestions),
                    )}
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
            </div>
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
            <button
              onClick={() => { setSkillsDraft(data.skills.join(", ")); setEditingSkills(true); }}
              className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 p-1 rounded text-slate-500 hover:text-amber-400 transition"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            {skillsSaved && <div className="mt-1"><SavedBadge /></div>}
          </div>
        )}
      </section>

      {/* ── Experience ───────────────────────────────────────────────────── */}
      {data.experience.length > 0 && (
        <section>
          <SectionHeader title="Experience" count={data.experience.length} />
          <div className="space-y-3">
            {data.experience.map((exp) => {
              const open = expandedExp === exp.company;
              const hasPendingHighlight =
                experienceSuggestions(suggestions, exp.company).some((s) => s.status === "pending");
              return (
                <div
                  key={exp.company}
                  className={`border rounded-xl overflow-hidden ${
                    hasPendingHighlight
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
                        <InlineFieldSuggestion
                          current={exp.title}
                          suggestion={titleSuggestion(suggestions, exp.company)}
                          label="title"
                          onAccept={acceptSug}
                          onReject={rejectSug}
                        />
                      </p>
                      <p className="text-slate-400 text-xs">
                        {exp.company} ·{" "}
                        <InlineFieldSuggestion
                          current={exp.dates}
                          suggestion={datesSuggestion(suggestions, exp.company)}
                          label="dates"
                          onAccept={acceptSug}
                          onReject={rejectSug}
                        />
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {exp.keywords_injected?.length > 0 && (
                        <span className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded px-1.5 py-0.5">
                          {exp.keywords_injected.length} kw injected
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
          <div className="space-y-3">
            {data.education.map((edu) => {
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
              return (
                <div
                  key={edu.institution}
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
                    <div className="flex items-center gap-2">
                      <GraduationCap className="w-4 h-4 text-slate-400 shrink-0" />
                      <div>
                        <p className="text-slate-100 text-sm font-semibold">{edu.degree}</p>
                        <p className="text-slate-400 text-xs">
                          <InlineFieldSuggestion
                            current={edu.institution}
                            suggestion={renameSug}
                            label="institution"
                            onAccept={acceptSug}
                            onReject={rejectSug}
                          />
                          {edu.year ? ` · ${edu.year}` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
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
                      <div>
                        <p className="text-xs text-slate-500 mb-1.5">Institution</p>
                        <InlineText
                          value={edu.institution}
                          onSave={(text) => saveEduInstitution(edu.institution, text)}
                          rows={1}
                          placeholder="School or program name"
                        />
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
                        addPlaceholder="e.g. Relevant coursework: Machine Learning, Distributed Systems · GPA: 3.9/4.0"
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
      {data.projects.length > 0 && (
        <section>
          <SectionHeader title="Projects" count={data.projects.length} />
          <div className="space-y-3">
            {data.projects.map((proj, i) => {
              const p = proj as Record<string, unknown>;
              const projectName = String(p.name ?? "");
              const bullets = (p.bullets as string[]) ?? [];
              const removalSug = projectRemovalPending(suggestions, projectName);
              const replaceAllSug = projectReplaceAllSuggestion(suggestions, projectName);
              const removalTone = removalSug?.status === "accepted"
                ? "accepted"
                : removalSug?.status === "pending"
                  ? "pending"
                  : "none";

              return (
                <div
                  key={i}
                  className={`border rounded-xl px-4 py-3 ${
                    removalTone === "pending"
                      ? "border-red-500/50 bg-red-950/20"
                      : removalTone === "accepted"
                        ? "border-emerald-500/40 bg-emerald-950/10 opacity-60"
                        : "border-slate-700 bg-slate-800/30"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <p className={`text-sm font-semibold ${
                      removalTone === "pending" ? "text-red-300 line-through" : "text-slate-100"
                    }`}>
                      {projectName}
                    </p>
                    {!!p.url && (
                      <a
                        href={String(p.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-slate-500 hover:text-amber-400 truncate max-w-[160px]"
                      >
                        {String(p.url)}
                      </a>
                    )}
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
                    bullets.map((b, j) => {
                      const editSug = projectBulletEditSuggestion(suggestions, projectName, b);
                      const acceptedSug = !editSug
                        ? acceptedProjectBulletSuggestion(suggestions, projectName, b)
                        : undefined;
                      const activeSug = editSug ?? acceptedSug;
                      const replaceAllAccepted =
                        replaceAllSug?.status === "accepted" &&
                        (replaceAllSug.patch.project_bullets_replace_all ?? []).some(
                          (text) => text === b,
                        );
                      const tone = replaceAllAccepted || activeSug?.status === "accepted"
                        ? "accepted"
                        : activeSug?.status === "pending"
                          ? "pending"
                          : "none";

                      if (activeSug && tone !== "none" && !replaceAllAccepted) {
                        return (
                          <SuggestedBulletRow
                            key={j}
                            suggestion={activeSug}
                            originalText={b}
                            displayText={b}
                            tone={tone}
                            onAccept={acceptSug}
                            onReject={rejectSug}
                          />
                        );
                      }

                      if (tone === "accepted") {
                        return (
                          <SuggestedBulletRow
                            key={j}
                            displayText={b}
                            tone="accepted"
                            onAccept={() => {}}
                            onReject={() => {}}
                          />
                        );
                      }

                      return (
                        <p key={j} className="text-slate-300 text-sm flex gap-2">
                          <span className="text-slate-600 shrink-0">•</span>
                          {b}
                        </p>
                      );
                    })
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
          {newProjectSuggestions(suggestions).map((sug) => (
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
      )}

      {orphanedSuggestions(suggestions, data).length > 0 && (
        <section>
          <SectionHeader title="AI Suggestions" count={orphanedSuggestions(suggestions, data).length} />
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

      {/* ── Certifications ───────────────────────────────────────────────── */}
      {data.certifications.length > 0 && (
        <section>
          <SectionHeader title="Certifications" />
          <div className="flex flex-wrap gap-1.5">
            {data.certifications.map((c, i) => (
              <span
                key={i}
                className="bg-slate-800 border border-slate-700 text-slate-300 rounded px-2.5 py-1 text-xs"
              >
                {c}
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
