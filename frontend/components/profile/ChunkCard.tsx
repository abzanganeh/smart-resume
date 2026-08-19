"use client"

import { useState } from "react"
import { Check, Pencil, Trash2, X } from "lucide-react"
import {
  deleteProfileChunk,
  estimateTokenCount,
  formatEmbeddingCost,
  patchProfileChunk,
  type ProfileChunk,
} from "@/lib/profile"
import { cn } from "@/lib/utils"

interface Props {
  chunk: ProfileChunk
  token: string
  onSaved: (updated: ProfileChunk) => void
  onDeleted: (chunkId: string) => void
}

export function ChunkCard({ chunk, token, onSaved, onDeleted }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(chunk.content)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isDeleted = Boolean(chunk.deleted_at)
  const previewTokens = estimateTokenCount(draft)
  const previewCost = formatEmbeddingCost(previewTokens)
  const contentChanged = draft.trim() !== chunk.content.trim()

  async function save() {
    if (!draft.trim() || isDeleted) return
    setSaving(true)
    setError(null)
    try {
      const updated = await patchProfileChunk(token, chunk.id, draft.trim())
      onSaved(updated)
      setEditing(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save chunk.")
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (isDeleted || deleting) return
    setDeleting(true)
    setError(null)
    try {
      await deleteProfileChunk(token, chunk.id)
      onDeleted(chunk.id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete chunk.")
    } finally {
      setDeleting(false)
    }
  }

  function cancelEdit() {
    setDraft(chunk.content)
    setEditing(false)
    setError(null)
  }

  return (
    <article
      data-chunk-id={chunk.id}
      data-section-type={chunk.section_type}
      className={cn(
        "rounded-xl border p-4 space-y-3 transition-opacity",
        isDeleted
          ? "border-slate-200 dark:border-slate-800 bg-white/40 dark:bg-slate-900/40 opacity-50"
          : "border-slate-300 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
          <span className="tabular-nums">
            {(editing ? previewTokens : chunk.token_count).toLocaleString()} tokens
          </span>
          {!isDeleted && editing && contentChanged && (
            <>
              <span aria-hidden>·</span>
              <span>embed ~{previewCost}</span>
            </>
          )}
          {isDeleted && (
            <span className="text-red-700 dark:text-red-400/80 font-medium">Deleted</span>
          )}
        </div>

        {!isDeleted && !editing && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-amber-800 dark:hover:text-amber-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="Edit chunk"
              aria-label="Edit chunk"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => void remove()}
              disabled={deleting}
              className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:text-red-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-40"
              title="Remove chunk"
              aria-label="Remove chunk"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {!editing ? (
        <p className="text-slate-800 dark:text-slate-200 text-sm whitespace-pre-wrap">{chunk.content}</p>
      ) : (
        <div className="space-y-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoFocus
            rows={4}
            className="w-full bg-slate-100 dark:bg-slate-800 border border-amber-400/50 rounded-lg px-3 py-2 text-slate-800 dark:text-slate-200 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-amber-400"
          />
          {contentChanged && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Save preview: {previewTokens} tokens · estimated cost {previewCost}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving || !draft.trim() || !contentChanged}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-400 text-slate-900 rounded-md text-xs font-semibold hover:bg-amber-300 disabled:opacity-40"
            >
              <Check className="w-3 h-3" />
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-md text-xs hover:bg-slate-300 dark:hover:bg-slate-600"
            >
              <X className="w-3 h-3" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-700 dark:text-red-400">{error}</p>}
    </article>
  )
}
