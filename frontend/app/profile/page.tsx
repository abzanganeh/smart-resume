"use client"

import { useCallback, useEffect, useMemo, useState, Suspense, useTransition } from "react"
import { useSession } from "next-auth/react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { ArrowLeft, ArrowRight, Loader2, RefreshCw, UserCircle, XCircle } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { patchOnboarding } from "@/lib/auth/api"
import { needsOnboarding, postOnboardingDestination } from "@/lib/auth/onboarding"
import { ChunkCard } from "@/components/profile/ChunkCard"
import { ProfileUploadZone } from "@/components/profile/ProfileUploadZone"
import { TailoredUsagePanel } from "@/components/profile/TailoredUsagePanel"
import {
  fetchTailoredResumeCount,
  getProfileChunks,
  getProfileResume,
  groupChunksBySection,
  liveChunkCount,
  reembedAllProfileResume,
  SECTION_LABELS,
  SECTION_ORDER,
  uploadProfileResume,
  type ProfileChunk,
  type ProfileResume,
} from "@/lib/profile"
import { clsx } from "clsx"

const REEMBED_THRESHOLD = 3

function formatTimestamp(iso: string | null): string {
  if (!iso) return "Never"
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

function ProfilePageContent() {
  const { session, status } = useRequireAuth("/profile")
  const { data: clientSession, update: updateSession } = useSession()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [isContinuing, startContinueTransition] = useTransition()

  const returnUrl = searchParams.get("return")
  const fromOnboarding = searchParams.get("from") === "onboarding"
  const defaultStory = searchParams.get("mode") === "story"

  const token = clientSession?.backendAccessToken ?? session?.backendAccessToken

  const [profile, setProfile] = useState<ProfileResume | null>(null)
  const [chunks, setChunks] = useState<ProfileChunk[]>([])
  const [tailoredCount, setTailoredCount] = useState<number | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [reembedding, setReembedding] = useState(false)
  const [editedChunkIds, setEditedChunkIds] = useState<Set<string>>(new Set())
  const [panelCollapsed, setPanelCollapsed] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadProfile = useCallback(async () => {
    if (!token) return
    setLoadingProfile(true)
    setError(null)
    try {
      const [resume, chunkRows, tailored] = await Promise.all([
        getProfileResume(token),
        getProfileChunks(token),
        fetchTailoredResumeCount(token),
      ])
      setProfile(resume)
      setChunks(chunkRows)
      setTailoredCount(tailored)
      setEditedChunkIds(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile")
    } finally {
      setLoadingProfile(false)
    }
  }, [token])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadProfile()
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [loadProfile])

  const grouped = useMemo(() => groupChunksBySection(chunks), [chunks])
  const liveCount = liveChunkCount(chunks)
  const showReembed =
    editedChunkIds.size >= REEMBED_THRESHOLD && Boolean(profile?.raw_text)
  const onboardingIncomplete = needsOnboarding(session?.backendUser)
  const showContinue =
    liveCount > 0 && (fromOnboarding || Boolean(returnUrl) || onboardingIncomplete)

  function handleContinue() {
    if (!token) return
    startContinueTransition(async () => {
      try {
        if (fromOnboarding && onboardingIncomplete) {
          router.push("/onboarding?step=4")
          return
        }
        if (onboardingIncomplete) {
          const user = await patchOnboarding(token, {
            ai_choice: "platform",
            complete: true,
          })
          await updateSession({ backendUser: user })
          window.location.assign(postOnboardingDestination(user))
          return
        }
        if (returnUrl) {
          router.push(returnUrl)
          return
        }
        router.push("/session/new")
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not continue")
      }
    })
  }

  async function handleUpload(payload: { file?: File; text?: string }) {
    if (!token) return
    setUploading(true)
    setError(null)
    try {
      const result = await uploadProfileResume(token, payload)
      setProfile(result)
      setChunks(result.chunks)
      setEditedChunkIds(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed")
      throw e
    } finally {
      setUploading(false)
    }
  }

  async function handleReembedAll() {
    if (!token || !profile?.raw_text) return
    setReembedding(true)
    setError(null)
    try {
      const result = await reembedAllProfileResume(token, profile.raw_text)
      setProfile(result)
      setChunks(result.chunks)
      setEditedChunkIds(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Re-embed failed")
    } finally {
      setReembedding(false)
    }
  }

  function handleChunkSaved(updated: ProfileChunk) {
    setChunks((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    setEditedChunkIds((prev) => {
      const next = new Set(prev)
      next.add(updated.id)
      return next
    })
    if (profile) {
      setProfile({ ...profile, last_embedded_at: new Date().toISOString() })
    }
  }

  function handleChunkDeleted(chunkId: string) {
    const now = new Date().toISOString()
    setChunks((prev) => {
      const next = prev.map((c) =>
        c.id === chunkId ? { ...c, deleted_at: now } : c,
      )
      if (profile) {
        setProfile({
          ...profile,
          chunk_count: liveChunkCount(next),
        })
      }
      return next
    })
  }

  if (status === "loading" || !session) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-600 dark:text-slate-400" />
      </div>
    )
  }

  const orderedSections = [
    ...SECTION_ORDER.filter((s) => grouped.has(s)),
    ...[...grouped.keys()].filter((s) => !SECTION_ORDER.includes(s as (typeof SECTION_ORDER)[number])),
  ]

  return (
    <main className="max-w-6xl mx-auto px-4 py-10">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </Link>
      <div className="flex flex-col lg:flex-row gap-8">
        <div className="flex-1 min-w-0 space-y-8">
          <header className="space-y-1">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <UserCircle className="w-7 h-7 text-amber-700 dark:text-amber-400" />
              Master resume profile
            </h1>
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Chunked, embedded career history used to tailor every session.
            </p>
          </header>

          {error && (
            <div className="bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm px-4 py-3 rounded-xl flex items-center gap-2">
              <XCircle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          <section className="bg-white/60 dark:bg-slate-900/60 border border-slate-300 dark:border-slate-700 rounded-2xl p-6">
            <ProfileUploadZone
              onSubmit={handleUpload}
              token={token ?? ""}
              loading={uploading}
              compact={liveCount > 0}
              defaultStory={defaultStory}
              onStoryComplete={() => {
                if (returnUrl) {
                  router.push(returnUrl)
                } else {
                  void loadProfile()
                }
              }}
            />
          </section>

          {loadingProfile ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-slate-600 dark:text-slate-400" />
            </div>
          ) : liveCount > 0 ? (
            <section className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-slate-600 dark:text-slate-400 space-y-0.5">
                  <p>
                    <span className="text-slate-800 dark:text-slate-200 font-medium tabular-nums">{liveCount}</span>{" "}
                    live chunk{liveCount === 1 ? "" : "s"}
                  </p>
                  <p>
                    Last embedded{" "}
                    <span className="text-slate-700 dark:text-slate-300">
                      {formatTimestamp(profile?.last_embedded_at ?? null)}
                    </span>
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {showContinue && (
                    <button
                      type="button"
                      onClick={handleContinue}
                      disabled={isContinuing || uploading || reembedding}
                      className="inline-flex items-center justify-center gap-2 bg-amber-400 text-slate-900 font-semibold text-sm px-4 py-2 rounded-xl hover:bg-amber-300 transition-colors disabled:opacity-60"
                    >
                      {isContinuing ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Continuing…
                        </>
                      ) : (
                        <>
                          {onboardingIncomplete ? "Continue setup" : "Continue"}
                          <ArrowRight className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  )}

                  {showReembed && (
                  <button
                    type="button"
                    onClick={() => void handleReembedAll()}
                    disabled={reembedding || uploading}
                    className={clsx(
                      "flex items-center gap-2 text-sm px-4 py-2 rounded-xl border transition-colors",
                      "border-amber-400/40 text-amber-700 dark:text-amber-400 hover:bg-amber-400/10",
                      "disabled:opacity-50",
                    )}
                  >
                    {reembedding ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <RefreshCw className="w-4 h-4" />
                    )}
                    Re-embed all
                  </button>
                  )}
                </div>
              </div>

              {showContinue && onboardingIncomplete && fromOnboarding && (
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Your master resume is indexed. Continue to the final onboarding step, then open your dashboard.
                </p>
              )}
              {showContinue && onboardingIncomplete && !fromOnboarding && (
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Your master resume is indexed. Finish setup to open your dashboard and start tailoring.
                </p>
              )}

              {orderedSections.map((sectionKey) => {
                const sectionChunks = grouped.get(sectionKey) ?? []
                if (sectionChunks.length === 0) return null
                const sectionLive = liveChunkCount(sectionChunks)

                return (
                  <div key={sectionKey} data-section={sectionKey} className="space-y-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
                      <h2 className="text-base font-semibold text-slate-900 dark:text-white">
                        {SECTION_LABELS[sectionKey] ?? sectionKey}
                      </h2>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        {sectionLive} chunk{sectionLive === 1 ? "" : "s"}
                        {profile?.last_embedded_at && (
                          <>
                            {" "}
                            · embedded {formatTimestamp(profile.last_embedded_at)}
                          </>
                        )}
                      </p>
                    </div>
                    <div className="grid gap-3">
                      {sectionChunks.map((chunk) => (
                        <ChunkCard
                          key={chunk.id}
                          chunk={chunk}
                          token={token!}
                          onSaved={handleChunkSaved}
                          onDeleted={handleChunkDeleted}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </section>
          ) : (
            !uploading && (
              <p className="text-center text-slate-600 dark:text-slate-400 text-sm py-8">
                No master resume yet — upload or paste above to get started.
              </p>
            )
          )}
        </div>

        <div className="lg:w-72 shrink-0">
          <TailoredUsagePanel
            count={tailoredCount}
            fallbackLabel={
              profile?.chunk_count
                ? `Profile ready · ${profile.chunk_count} chunk${profile.chunk_count === 1 ? "" : "s"} indexed`
                : undefined
            }
            collapsed={panelCollapsed}
            onToggle={() => setPanelCollapsed((v) => !v)}
          />
        </div>
      </div>
    </main>
  )
}

export default function ProfilePage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-6 h-6 animate-spin text-slate-600 dark:text-slate-400" />
        </div>
      }
    >
      <ProfilePageContent />
    </Suspense>
  )
}
