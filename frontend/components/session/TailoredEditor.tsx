"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  GraduationCap,
  Info,
  Pencil,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { patchTailoredResume, type TailoredResumeOutput } from "@/lib/api";

interface Props {
  initial: TailoredResumeOutput;
  sessionId: string;
  onSaved?: (updated: TailoredResumeOutput) => void;
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

// ── main component ────────────────────────────────────────────────────────────

export function TailoredEditor({ initial, sessionId, onSaved }: Props) {
  const [data, setData] = useState<TailoredResumeOutput>(initial);
  const [expandedExp, setExpandedExp] = useState<string | null>(
    initial.experience[0]?.company ?? null
  );
  const [expandedEdu, setExpandedEdu] = useState<string | null>(null);
  const [showNotes, setShowNotes] = useState(false);

  async function patch(payload: Record<string, unknown>) {
    const result = await patchTailoredResume(sessionId, payload);
    return result;
  }

  function updateLocal(updater: (prev: TailoredResumeOutput) => TailoredResumeOutput) {
    setData((prev) => {
      const next = updater(prev);
      onSaved?.(next);
      return next;
    });
  }

  // ── Summary ──────────────────────────────────────────────────────────────

  async function saveSummary(text: string) {
    await patch({ section: "summary", new_text: text });
    updateLocal((p) => ({ ...p, summary: text }));
  }

  // ── Skills ───────────────────────────────────────────────────────────────

  async function saveSkills(skills: string[]) {
    await patch({ section: "skills", skills });
    updateLocal((p) => ({ ...p, skills }));
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
  }

  async function deleteExpBullet(company: string, idx: number) {
    const entry = data.experience.find((e) => e.company === company);
    if (!entry) return;
    const bullets = entry.bullets.filter((_, i) => i !== idx);
    await patch({ section: "skills", skills: data.skills }); // flush via skills as workaround
    // Use education_bullets pattern for proper update
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

  return (
    <div className="space-y-8">

      {/* ── Summary ──────────────────────────────────────────────────────── */}
      <section>
        <SectionHeader title="Professional Summary" />
        <InlineText
          value={data.summary}
          onSave={saveSummary}
          rows={4}
          placeholder="2–3 sentences, max 60 words, include 3–4 exact JD keywords."
        />
      </section>

      {/* ── Skills ───────────────────────────────────────────────────────── */}
      <section>
        <SectionHeader title="Skills" count={data.skills.length} />
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
              {data.skills.map((s, i) => (
                <span
                  key={i}
                  className="bg-slate-800 border border-slate-700 text-slate-300 rounded px-2 py-0.5 text-xs"
                >
                  {s}
                </span>
              ))}
            </div>
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
              return (
                <div key={exp.company} className="border border-slate-700 rounded-xl overflow-hidden">
                  <button
                    onClick={() => setExpandedExp(open ? null : exp.company)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-800 text-left transition"
                  >
                    <div>
                      <p className="text-slate-100 text-sm font-semibold">{exp.title}</p>
                      <p className="text-slate-400 text-xs">{exp.company} · {exp.dates}</p>
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
                      <BulletList
                        bullets={exp.bullets}
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
              return (
                <div key={edu.institution} className="border border-slate-700 rounded-xl overflow-hidden">
                  <button
                    onClick={() => setExpandedEdu(open ? null : edu.institution)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-800 text-left transition"
                  >
                    <div className="flex items-center gap-2">
                      <GraduationCap className="w-4 h-4 text-slate-400 shrink-0" />
                      <div>
                        <p className="text-slate-100 text-sm font-semibold">{edu.degree}</p>
                        <p className="text-slate-400 text-xs">
                          {edu.institution}
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
                    <div className="px-4 py-4 bg-slate-900/40">
                      {edu.bullets.length === 0 && (
                        <p className="text-slate-600 text-xs mb-3 flex items-center gap-1.5">
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
              const bullets = (p.bullets as string[]) ?? [];
              return (
                <div key={i} className="border border-slate-700 rounded-xl px-4 py-3 bg-slate-800/30">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-slate-100 text-sm font-semibold">{String(p.name ?? "")}</p>
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
                  {bullets.map((b, j) => (
                    <p key={j} className="text-slate-300 text-sm flex gap-2">
                      <span className="text-slate-600 shrink-0">•</span>
                      {b}
                    </p>
                  ))}
                </div>
              );
            })}
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
