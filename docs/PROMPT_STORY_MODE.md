# Implementation Prompt — Story Mode
## "Tell your story. Get a professional resume."

**Branch:** `feature/story-mode`  
**Target:** Merges to `main` after CI passes (unit-tests → build → staging deploy)  
**Base design doc:** `docs/SYSTEM_DESIGN_PHASE_2.md §21`

---

## Role & Context

You are a Staff Engineer implementing the **Story Mode** feature for Smart Resume Agent. This is the product's flagship differentiator: users speak naturally about their career, and the platform converts the spoken narrative into a structured master resume.

Before touching any file, read these in full:

1. `docs/SYSTEM_DESIGN_PHASE_2.md` — especially §20 (what's already implemented) and §21 (the plan you are implementing)
2. `backend/app/routers/profile.py` — existing profile upload endpoint
3. `backend/app/services/master_resume/crud.py` — chunking + embedding pipeline
4. `backend/app/services/billing/quota.py` — credit system (`QuotaAction`, `FREE_CREDIT_ACTIONS`, `consume_credit`)
5. `frontend/components/profile/ProfileUploadZone.tsx` — current profile upload UI
6. `frontend/components/shared/VoiceTab.tsx` — existing shared voice component
7. `frontend/hooks/useVoiceRecorder.ts` — existing voice state machine

Do **NOT** modify §18 / §19 of the system design. Do **NOT** break the existing upload/paste/voice tabs. Do **NOT** change the session-level resume pipeline (phases 1–4).

---

## What to Build

### Summary

Implement a segmented voice story recording flow on the `/profile` page. Users record up to 30 × 60-second segments (30 min cap). After finishing, they click "Generate resume from story" which calls a new backend endpoint that converts the narrative to a master resume via a two-step LLM pipeline. Add credit logic, promotional surfaces, and full test coverage.

---

## Part 1 — Backend

### 1.1 Prompt file

**Create:** `backend/app/agent/prompts/story_to_resume.txt`

```
You are a professional resume writer. The user has recorded a spoken story about their career.

RAW STORY:
{narrative}

Your task:
1. Extract all career information from the story: job titles, companies, dates, responsibilities, accomplishments, skills, education, certifications, and projects.
2. Rewrite this information as clean, professional resume text organized in standard sections.
3. Use strong action verbs and professional tone.
4. Do NOT invent facts, metrics, or experiences the user did not mention.
5. Do NOT add placeholders like "[Company Name]" — if information is missing, omit that field entirely.
6. Output sections in this order (omit sections the user did not mention):
   - Professional Summary (2–3 sentences)
   - Skills (comma-separated list)
   - Experience (company, title, dates, bullet points)
   - Education (institution, degree, year)
   - Projects (name, description, tech stack)
   - Certifications (name, issuer, year)

Output plain text only. No markdown headers. No JSON. Use this exact section format:

PROFESSIONAL SUMMARY
[text]

SKILLS
[comma-separated list]

EXPERIENCE
[Company Name] | [Job Title] | [Start Date] – [End Date]
• [bullet]
• [bullet]

EDUCATION
[Institution] | [Degree] | [Year]

PROJECTS
[Project Name]
• [description]
• [tech stack]

CERTIFICATIONS
[Name] | [Issuer] | [Year]
```

**Validation:**
- The placeholder `{narrative}` must appear exactly once.
- Sections must be separated by a blank line.

---

### 1.2 Story LLM agent

**Create:** `backend/app/agent/story.py`

```python
"""Convert a raw spoken career narrative to structured resume text.

Step 1 of the story-to-resume pipeline. Step 2 reuses the existing
parse_resume infrastructure.
"""
from __future__ import annotations

import structlog
from pathlib import Path

from app.llm.base import LLMClient

log = structlog.get_logger("agent.story")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "story_to_resume.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def story_to_resume(
    narrative: str,
    llm_client: LLMClient,
    *,
    max_output_tokens: int = 1500,
) -> str:
    """
    Convert a raw spoken narrative to structured resume draft text.

    Args:
        narrative: Joined transcript from all story segments.
        llm_client: Resolved LLM client (BYOK or platform default).
        max_output_tokens: Cap for output tokens (resume text is ~800 words).

    Returns:
        Plain-text resume draft ready for the existing parse_resume pipeline.

    Raises:
        RuntimeError: If the LLM response is empty or too short to be a resume.
    """
    prompt_template = _load_prompt()
    prompt = prompt_template.replace("{narrative}", narrative)

    log.info("story.convert_start", narrative_chars=len(narrative))

    # Use simple text completion (not structured output — we want free-form text).
    response = await llm_client.complete(
        system="You are a professional resume writer.",
        user=prompt,
        max_tokens=max_output_tokens,
    )

    draft = response.strip() if response else ""

    if len(draft) < 100:
        raise RuntimeError(
            f"story_to_resume: LLM returned unexpectedly short output ({len(draft)} chars). "
            "The narrative may be too short or the LLM may have failed."
        )

    log.info("story.convert_done", draft_chars=len(draft))
    return draft
```

**Note on `llm_client.complete()`:** This is a non-structured text completion. Check `backend/app/llm/base.py` for the exact method signature — it may be `generate()`, `chat()`, or similar. Adapt the call to match the existing interface. Do NOT introduce a new method on the base class; use whichever text-completion method already exists.

---

### 1.3 Pydantic models

**Create:** `backend/app/models/story.py`

```python
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class StoryToResumeRequest(BaseModel):
    segments: list[str] = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Transcript text per segment, in recording order.",
    )
    whisper_path: bool = Field(
        default=False,
        description="True when the Whisper transcription path was used (Firefox/Safari). "
                    "Used for credit routing.",
    )

    @model_validator(mode="after")
    def validate_content(self) -> "StoryToResumeRequest":
        total_words = sum(len(s.split()) for s in self.segments)
        if total_words < 50:
            raise ValueError(
                "Story is too short. Please record at least 50 words across all segments."
            )
        return self
```

---

### 1.4 Credit routing

**Modify:** `backend/app/services/billing/quota.py`

Add `story_build` to the `QuotaAction` enum:

```python
class QuotaAction(str, enum.Enum):
    resume_build   = "resume_build"
    ats_recalc     = "ats_recalc"
    cover_letter   = "cover_letter"
    section_regen  = "section_regen"
    story_build    = "story_build"   # ← NEW
```

Add `story_build` to `FREE_CREDIT_ACTIONS` (free users can spend credits on story builds):

```python
FREE_CREDIT_ACTIONS: frozenset[QuotaAction] = frozenset({
    QuotaAction.resume_build,
    QuotaAction.ats_recalc,
    QuotaAction.cover_letter,
    QuotaAction.section_regen,
    QuotaAction.story_build,    # ← NEW
})
```

Add the new quota check function at the bottom of the file:

```python
async def check_quota_for_story(
    session: AsyncSession,
    *,
    user: User,
    whisper_path: bool,
    byok_active: bool,
    session_id: str | None = None,
) -> QuotaDecision:
    """Quota for story-mode resume generation.

    Credit cost:
      - BYOK (any browser):           0 credits — user pays their own LLM costs
      - Platform LLM + Web Speech:    0 credits — transcription is browser-native; LLM cost ~$0.001
      - Platform LLM + Whisper:       2 credits — Whisper transcription costs ~$0.12 for 20 min

    Subscribers always pay 0 credits for story builds (subscription covers usage).
    """
    if user.is_suspended:
        raise AccountSuspendedError("account_suspended")

    # BYOK users: always free
    if byok_active:
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="byok",
        )

    # Subscribers: free within subscription
    sub = await _active_subscription_for(session, user_id=user.id)
    now = datetime.now(timezone.utc)
    if sub is not None and _within_period(sub, now=now) and sub.status != SubscriptionStatus.paused:
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="subscription",
            subscription_id=sub.id,
        )

    # Web Speech path: free for free users
    if not whisper_path:
        return QuotaDecision(
            action=QuotaAction.story_build,
            charged_to="free_web_speech",
        )

    # Whisper path: costs 2 credits
    WHISPER_CREDIT_COST = 2
    try:
        row = await consume_credit(
            session,
            user_id=user.id,
            credit_kind=CreditKind.free,
            reason=QuotaAction.story_build.value,
            session_id=session_id,
            amount=WHISPER_CREDIT_COST,
        )
    except InsufficientCreditsError:
        raise

    return QuotaDecision(
        action=QuotaAction.story_build,
        charged_to="free_credit",
        credit_transaction_id=row.id,
    )
```

**Note:** If `consume_credit` does not accept an `amount` parameter, check its signature in `credits.py` and either add it or call it twice. Do not guess.

---

### 1.5 New endpoint

**Modify:** `backend/app/routers/profile.py`

Add after the existing `POST /api/profile/resume` endpoint:

```python
@router.post("/resume/from-story", status_code=200)
@limiter.limit("5/minute")
async def create_resume_from_story(
    request: Request,
    body: StoryToResumeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
) -> dict:
    """
    Convert a spoken career narrative (list of segment transcripts) to a
    structured master resume via a two-step LLM pipeline:
      Step 1: story_to_resume() — narrative → resume draft text
      Step 2: existing parse_resume pipeline — draft → ParsedResume + chunks + embeddings

    Credit rules: see check_quota_for_story() in quota.py.
    """
    # ── Resolve LLM client ────────────────────────────────────────────────────
    byok_key = request.headers.get("X-Api-Key", "").strip()
    provider  = request.headers.get("X-Provider", "").strip()
    model     = request.headers.get("X-Model", "").strip()
    byok_active = bool(byok_key and provider and model)

    llm_client = get_llm_client(
        api_key=byok_key or None,
        provider=provider or None,
        model=model or None,
    )

    # ── Credit check ──────────────────────────────────────────────────────────
    await check_quota_for_story(
        db,
        user=user,
        whisper_path=body.whisper_path,
        byok_active=byok_active,
    )

    # ── Step 1: narrative → resume draft text ─────────────────────────────────
    narrative = "\n\n---\n\n".join(seg.strip() for seg in body.segments if seg.strip())

    try:
        draft_text = await story_to_resume(narrative, llm_client)
    except Exception as exc:
        log.error("story.convert_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"code": "story_conversion_failed", "message": str(exc)},
        )

    # ── Step 2: draft text → ParsedResume + chunks + embeddings ──────────────
    # Reuse the same path as POST /api/profile/resume with text input.
    try:
        resume, chunks, embedding_ok = await master_crud.create_or_replace_from_text(
            db,
            user_id=user.id,
            raw_text=draft_text,
        )
    except Exception as exc:
        log.error("story.parse_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"code": "parse_failed", "message": str(exc)},
        )

    return {
        **_resume_to_response(resume),
        "chunks": master_crud.iter_chunk_summaries(chunks),
        "embedding_warning": (
            None if embedding_ok
            else "Resume saved but embedding failed. Semantic similarity features won't work "
                 "until OPENAI_EMBEDDING_KEY is configured."
        ),
    }
```

Add imports at the top of the file:
```python
from app.agent.story import story_to_resume
from app.models.story import StoryToResumeRequest
from app.services.billing.quota import check_quota_for_story
```

---

## Part 2 — Frontend

### 2.1 API helper

**Create:** `frontend/lib/story.ts`

```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface StoryToResumeResponse {
  id: string;
  chunk_count: number;
  last_embedded_at: string | null;
  embedding_warning: string | null;
}

export async function submitStory(
  segments: string[],
  token: string,
  options: {
    byokApiKey?: string;
    byokProvider?: string;
    byokModel?: string;
    whisperPath?: boolean;
  } = {},
): Promise<StoryToResumeResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (options.byokApiKey)   headers["X-Api-Key"]   = options.byokApiKey;
  if (options.byokProvider) headers["X-Provider"]  = options.byokProvider;
  if (options.byokModel)    headers["X-Model"]     = options.byokModel;

  const res = await fetch(`${BASE}/api/profile/resume/from-story`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      segments,
      whisper_path: options.whisperPath ?? false,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: { message?: string } | string };
    const msg = typeof body.detail === "object"
      ? (body.detail?.message ?? "Story conversion failed")
      : (body.detail ?? "Story conversion failed");
    throw new Error(msg);
  }

  return res.json() as Promise<StoryToResumeResponse>;
}
```

---

### 2.2 Single segment component

**Create:** `frontend/components/profile/StorySegment.tsx`

```typescript
"use client";

import { Mic, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  index: number;          // 0-based
  text: string;
  isRecording: boolean;   // this segment is currently being re-recorded
  disabled: boolean;
  onChange: (text: string) => void;
  onReRecord: () => void;
  onDelete: () => void;
}

export function StorySegment({ index, text, isRecording, disabled, onChange, onReRecord, onDelete }: Props) {
  const preview = text.slice(0, 80) + (text.length > 80 ? "…" : "");

  return (
    <div className={cn(
      "rounded-xl border p-4 space-y-2 transition-colors",
      isRecording ? "border-red-500/50 bg-red-500/5" : "border-slate-700 bg-slate-800/40",
    )}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
          Segment {index + 1}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onReRecord}
            disabled={disabled}
            title="Re-record this segment"
            className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-slate-700 disabled:opacity-40 transition-colors"
          >
            <Mic className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={disabled}
            title="Delete this segment"
            className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-slate-700 disabled:opacity-40 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {isRecording ? (
        <p className="text-red-400 text-xs italic animate-pulse">Recording…</p>
      ) : (
        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          rows={3}
          placeholder="Segment transcript will appear here…"
          className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-slate-200 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600 disabled:opacity-60"
        />
      )}

      {!isRecording && text.length === 0 && (
        <p className="text-slate-600 text-xs italic">{preview || "Empty segment"}</p>
      )}
    </div>
  );
}
```

---

### 2.3 Story recorder component

**Create:** `frontend/components/profile/StoryRecorder.tsx`

This is the main component. Implement it with the following structure and behavior. **Write the full implementation** — do not leave TODOs.

```typescript
"use client";

/**
 * StoryRecorder — segmented voice story recording UI.
 *
 * Max 30 segments × 60 seconds = 30 min.
 * Each segment is editable after recording.
 * "Generate resume from story" calls POST /api/profile/resume/from-story.
 *
 * Credit path:
 *   - Web Speech (Chrome/Edge): 0 credits
 *   - Whisper fallback (Firefox/Safari): 2 credits — shown in disclosure before start
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Sparkles, Clock } from "lucide-react";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { StorySegment } from "./StorySegment";
import { submitStory } from "@/lib/story";
import { getStoredKey } from "@/lib/keyStore";
import { cn } from "@/lib/utils";

const MAX_SEGMENTS = 30;
const SEGMENT_DURATION_MS = 60_000; // 60 seconds
const WARN_TOTAL_MS = 18 * 60 * 1000; // 18 min
const MAX_TOTAL_MS  = 30 * 60 * 1000; // 30 min

interface Props {
  token: string;
  onSaved: () => void; // called after successful save → parent refreshes profile
}

type RecordingState = "idle" | "recording" | "re-recording"; // "re-recording" = re-record segment N

export function StoryRecorder({ token, onSaved }: Props) {
  const [segments, setSegments] = useState<string[]>([]);
  const [recordingState, setRecordingState]   = useState<RecordingState>("idle");
  const [reRecordingIndex, setReRecordingIndex] = useState<number | null>(null);
  const [totalMs, setTotalMs] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const totalTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const totalStartRef = useRef<number>(0);

  // useVoiceRecorder: used for each individual segment recording
  const { voiceState, finalText, interimText, durationLabel, supportsWebSpeech,
          start, stop, reset: resetVoice, setFinalText } = useVoiceRecorder({
    onBlob: async (blob) => {
      // Whisper fallback — send audio to backend
      const ext = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "mp4" : "webm";
      const form = new FormData();
      form.append("audio", blob, `recording.${ext}`);
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      const key = getStoredKey();
      if (key?.apiKey) headers["X-Api-Key"] = key.apiKey;
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/profile/resume/transcribe`, {
        method: "POST", headers, body: form,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { text: string };
      setFinalText(data.text);
    },
  });

  // ── Total time tracker ─────────────────────────────────────────────────────
  const startTotalTimer = () => {
    totalStartRef.current = Date.now() - totalMs;
    totalTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - totalStartRef.current;
      setTotalMs(elapsed);
      if (elapsed >= MAX_TOTAL_MS) {
        // Hard stop — force end segment
        void stop();
      }
    }, 500);
  };

  const stopTotalTimer = () => {
    if (totalTimerRef.current) { clearInterval(totalTimerRef.current); totalTimerRef.current = null; }
  };

  useEffect(() => () => stopTotalTimer(), []);

  // ── Auto-stop segment at 60s ───────────────────────────────────────────────
  const segmentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearSegmentTimer = () => {
    if (segmentTimerRef.current) { clearTimeout(segmentTimerRef.current); segmentTimerRef.current = null; }
  };

  // ── Start recording a new segment ─────────────────────────────────────────
  const startNewSegment = useCallback(async () => {
    if (segments.length >= MAX_SEGMENTS) return;
    setError(null);
    resetVoice();
    setRecordingState("recording");
    startTotalTimer();
    await start();
    // Auto-stop after 60 seconds
    segmentTimerRef.current = setTimeout(() => { void stopCurrentSegment(); }, SEGMENT_DURATION_MS);
  }, [segments.length, start, resetVoice]);

  // ── Stop current segment and commit ───────────────────────────────────────
  const stopCurrentSegment = useCallback(async () => {
    clearSegmentTimer();
    stopTotalTimer();
    await stop();
    // finalText is now set (Web Speech) or will be set after onBlob (Whisper)
    // voiceState will transition to "preview" via the hook
  }, [stop]);

  // When voiceState reaches "preview", commit the segment
  useEffect(() => {
    if (voiceState !== "preview") return;
    const text = finalText.trim();
    if (!text) return;

    if (recordingState === "re-recording" && reRecordingIndex !== null) {
      setSegments((prev) => prev.map((s, i) => i === reRecordingIndex ? text : s));
      setReRecordingIndex(null);
    } else {
      setSegments((prev) => [...prev, text]);
    }
    setRecordingState("idle");
    resetVoice();
  }, [voiceState]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Re-record a specific segment ──────────────────────────────────────────
  const startReRecord = async (index: number) => {
    resetVoice();
    setReRecordingIndex(index);
    setRecordingState("re-recording");
    setError(null);
    await start();
    segmentTimerRef.current = setTimeout(() => { void stopCurrentSegment(); }, SEGMENT_DURATION_MS);
  };

  // ── Delete a segment ──────────────────────────────────────────────────────
  const deleteSegment = (index: number) => {
    setSegments((prev) => prev.filter((_, i) => i !== index));
  };

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (segments.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const key = getStoredKey();
      await submitStory(segments, token, {
        byokApiKey: key?.apiKey,
        byokProvider: key?.provider,
        byokModel: key?.model,
        whisperPath: !supportsWebSpeech,
      });
      setSuccess(true);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate resume from story.");
    } finally {
      setSubmitting(false);
    }
  };

  const isRecordingAnything = recordingState !== "idle";
  const canAddSegment = segments.length < MAX_SEGMENTS && !isRecordingAnything && !submitting;
  const totalMinsLabel = `${Math.floor(totalMs / 60000)}:${String(Math.floor((totalMs % 60000) / 1000)).padStart(2, "0")}`;
  const isWarning = totalMs >= WARN_TOTAL_MS;

  // ── Credit disclosure (shown before first segment) ─────────────────────────
  if (segments.length === 0 && !isRecordingAnything) {
    return (
      <div className="space-y-6">
        <div className={cn(
          "rounded-xl border p-5 space-y-3",
          supportsWebSpeech ? "border-green-500/30 bg-green-500/5" : "border-amber-500/30 bg-amber-500/5",
        )}>
          <div className="flex items-center gap-2">
            <Mic className={cn("w-4 h-4", supportsWebSpeech ? "text-green-400" : "text-amber-400")} />
            <span className={cn("font-semibold text-sm", supportsWebSpeech ? "text-green-400" : "text-amber-400")}>
              {supportsWebSpeech ? "Live transcription — free, no API key needed" : "AI transcription via Whisper"}
            </span>
          </div>
          {supportsWebSpeech ? (
            <p className="text-slate-400 text-sm">
              Your browser supports live transcription. Words appear as you speak. Generating your resume from story: <strong className="text-white">0 credits</strong>.
            </p>
          ) : (
            <div className="space-y-2">
              <p className="text-slate-400 text-sm">
                Your browser does not support live transcription. We'll use Whisper AI to transcribe each segment.
                Cost: <strong className="text-white">2 credits per story</strong>.
              </p>
              <p className="text-slate-500 text-xs">
                Switch to Chrome or Edge to record for free.
              </p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-5 space-y-2">
          <p className="text-slate-300 font-medium text-sm">How it works</p>
          <ol className="text-slate-400 text-sm space-y-1 list-decimal list-inside">
            <li>Record up to 30 segments of 60 seconds each (30 min total)</li>
            <li>Talk naturally — jobs, skills, accomplishments, education</li>
            <li>Edit any segment after recording</li>
            <li>Click "Generate resume from story" when done</li>
          </ol>
          <p className="text-slate-500 text-xs pt-1">
            <Clock className="w-3 h-3 inline mr-1" />
            Most people finish in 10–15 minutes
          </p>
        </div>

        <button
          type="button"
          onClick={() => void startNewSegment()}
          className="w-full py-4 bg-red-500 hover:bg-red-400 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
        >
          <Mic className="w-5 h-5" />
          {supportsWebSpeech ? "Start your story — free" : `Start your story — 2 credits`}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-3 px-1">
        <span className="text-slate-400 text-sm">
          <span className="text-white font-semibold">{segments.length}</span> / {MAX_SEGMENTS} segments
        </span>
        <span className={cn("text-sm tabular-nums font-mono", isWarning ? "text-amber-400" : "text-slate-400")}>
          {totalMinsLabel} / 30:00
          {isWarning && <span className="ml-2 text-amber-400 text-xs">⚠ Almost at limit</span>}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", isWarning ? "bg-amber-400" : "bg-amber-400/60")}
          style={{ width: `${Math.min((totalMs / MAX_TOTAL_MS) * 100, 100)}%` }}
        />
      </div>

      {/* Segment list */}
      <div className="space-y-3">
        {segments.map((text, i) => (
          <StorySegment
            key={i}
            index={i}
            text={text}
            isRecording={recordingState === "re-recording" && reRecordingIndex === i}
            disabled={isRecordingAnything || submitting}
            onChange={(newText) => setSegments((prev) => prev.map((s, j) => j === i ? newText : s))}
            onReRecord={() => void startReRecord(i)}
            onDelete={() => deleteSegment(i)}
          />
        ))}
      </div>

      {/* Current recording indicator (new segment) */}
      {recordingState === "recording" && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
            </span>
            <span className="text-red-400 text-sm font-medium">
              Recording segment {segments.length + 1} · {durationLabel}
            </span>
            <button
              type="button"
              onClick={() => void stopCurrentSegment()}
              className="ml-auto px-3 py-1 bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold rounded-full transition-colors"
            >
              Done
            </button>
          </div>
          {/* Live transcript */}
          <div className="min-h-12 text-sm leading-relaxed pl-1">
            <span className="text-slate-200">{finalText}</span>
            {finalText && interimText && " "}
            {interimText && <span className="text-slate-500 italic">{interimText}</span>}
            {!finalText && !interimText && (
              <span className="text-slate-600 italic">Start speaking…</span>
            )}
          </div>
        </div>
      )}

      {/* Whisper transcribing */}
      {voiceState === "transcribing" && (
        <div className="flex items-center gap-2 text-slate-400 text-sm py-3 justify-center">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          Transcribing segment with Whisper…
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-3 pt-2">
        {canAddSegment && (
          <button
            type="button"
            onClick={() => void startNewSegment()}
            className="flex-1 py-3 border border-slate-700 hover:border-amber-400/50 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-2 text-sm"
          >
            <Mic className="w-4 h-4" />
            {segments.length === 0 ? "Start recording" : "Record next segment"}
          </button>
        )}

        {segments.length > 0 && !isRecordingAnything && (
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting}
            className="flex-1 py-3 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 disabled:opacity-50 text-sm"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
                Generating resume…
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Generate resume from story
              </>
            )}
          </button>
        )}
      </div>

      {error && (
        <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          {error}
        </div>
      )}

      {success && (
        <div className="text-green-400 text-sm bg-green-400/10 border border-green-400/20 rounded-lg p-3">
          Your story has been turned into a professional profile. Redirecting…
        </div>
      )}
    </div>
  );
}
```

---

### 2.4 Update ProfileUploadZone

**Modify:** `frontend/components/profile/ProfileUploadZone.tsx`

1. Add "Tell your story" as the **first tab** in the mode list.
2. Import and render `StoryRecorder` when `mode === "story"`.
3. Default mode: if `props.defaultStory` is true (or no master resume exists, passed as a prop), set initial `mode` state to `"story"`.

```typescript
type Mode = "story" | "upload" | "paste" | "voice"

// Add prop:
interface Props {
  onSubmit: (payload: { file?: File; text?: string }) => Promise<void>
  token: string
  loading: boolean
  compact?: boolean
  defaultStory?: boolean  // ← NEW: true when user has no master resume
  onStoryComplete?: () => void  // ← NEW: called after story save
}

// Tab order:
const TABS: { id: Mode; label: string }[] = [
  { id: "story",  label: "🎙 Tell your story" },
  { id: "upload", label: "Upload file" },
  { id: "paste",  label: "Paste text" },
  { id: "voice",  label: "Record voice" },
]

// Initial mode:
const [mode, setMode] = useState<Mode>(defaultStory ? "story" : "upload")
```

Render story tab panel:
```tsx
{mode === "story" && (
  <StoryRecorder
    token={token}
    onSaved={() => {
      onStoryComplete?.()
    }}
  />
)}
```

---

### 2.5 Profile page — URL param support

**Modify:** `frontend/app/profile/page.tsx`

Read `?mode=story` and `?return=` URL params on mount:

```typescript
// At the top of the page component:
const searchParams = useSearchParams()
const returnUrl = searchParams.get("return")
const defaultStory = searchParams.get("mode") === "story"

// Pass to ProfileUploadZone:
<ProfileUploadZone
  defaultStory={defaultStory}
  onStoryComplete={() => {
    if (returnUrl) {
      router.push(returnUrl)
    } else {
      // refresh profile data
      void fetchResume()
    }
  }}
  // ... other props
/>
```

---

### 2.6 Dashboard — story CTA empty state

**Modify:** `frontend/app/dashboard/page.tsx`

When `has_master_resume === false` (check the dashboard API response for this field or infer from `master_resume_chunks === 0`), render a CTA block **at the top of the page body** (below the welcome header, above the resume history list):

```tsx
{!hasMasterResume && (
  <div className="rounded-2xl border border-amber-400/20 bg-amber-400/5 p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4">
    <div className="flex-1 space-y-1">
      <p className="text-white font-semibold text-lg">Ready to build your master resume?</p>
      <p className="text-slate-400 text-sm">
        Skip the formatting. Just tell your story — jobs, skills, and experience out loud.
        We'll turn it into a professional profile in 10–15 minutes.
      </p>
    </div>
    <div className="flex flex-col gap-2 shrink-0">
      <a
        href="/profile?mode=story"
        className="px-5 py-2.5 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-colors text-sm text-center"
      >
        Start your story →
      </a>
      <a
        href="/profile"
        className="px-5 py-2 text-slate-400 hover:text-white text-sm text-center transition-colors"
      >
        Upload file instead
      </a>
    </div>
  </div>
)}
```

---

### 2.7 Session wizard — promotional card

**Modify:** `frontend/app/session/new/page.tsx` and/or `frontend/components/wizard/ResumeUploader.tsx`

Add a promotional card **above** the upload tabs, shown only when the user has no saved master resume (pass `hasMasterResume` as a prop from the page):

```tsx
{!hasMasterResume && (
  <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 flex items-start gap-3">
    <span className="text-2xl">🎙</span>
    <div className="flex-1 space-y-1">
      <p className="text-white font-medium text-sm">Don't have a resume file yet?</p>
      <p className="text-slate-400 text-xs">
        Build your master profile by telling your story first — 10–20 minutes of speaking → a complete resume.
      </p>
    </div>
    <a
      href={`/profile?mode=story&return=/session/new`}
      target="_blank"
      className="shrink-0 px-3 py-1.5 bg-amber-400 text-slate-900 text-xs font-semibold rounded-lg hover:bg-amber-300 transition-colors"
    >
      Go to Story Mode →
    </a>
  </div>
)}
```

---

## Part 3 — Tests

### 3.1 Backend unit tests

**Create:** `backend/tests/unit/test_story.py`

```python
"""Unit tests for agent/story.py"""
import pytest
from unittest.mock import AsyncMock, patch
from app.agent.story import story_to_resume

MOCK_DRAFT = """
PROFESSIONAL SUMMARY
Experienced software engineer with 5 years in ML infrastructure.

SKILLS
Python, AWS, TensorFlow

EXPERIENCE
SecureAuth | Senior Engineer | 2022 – 2025
• Built anomaly detection pipelines
"""


@pytest.mark.asyncio
async def test_story_to_resume_calls_llm():
    """story_to_resume passes joined narrative to LLM and returns its output."""
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=MOCK_DRAFT)

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        result = await story_to_resume("I worked at SecureAuth for three years.", mock_client)

    assert "PROFESSIONAL SUMMARY" in result
    mock_client.complete.assert_called_once()
    call_kwargs = mock_client.complete.call_args
    # Narrative must appear in the user message
    assert "I worked at SecureAuth" in str(call_kwargs)


@pytest.mark.asyncio
async def test_story_to_resume_raises_on_empty_llm_output():
    """story_to_resume raises RuntimeError when LLM returns empty string."""
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value="")

    with patch("app.agent.story._load_prompt", return_value="Narrative: {narrative}"):
        with pytest.raises(RuntimeError, match="unexpectedly short"):
            await story_to_resume("Some narrative text here.", mock_client)


def test_story_prompt_file_exists_and_has_placeholder():
    """story_to_resume.txt must exist and contain the {narrative} placeholder."""
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent.parent / "app" / "agent" / "prompts" / "story_to_resume.txt"
    assert prompt_path.exists(), "story_to_resume.txt must exist"
    content = prompt_path.read_text()
    assert "{narrative}" in content, "Prompt must contain {narrative} placeholder"
```

**Create / modify:** `backend/tests/integration/test_profile_story.py`

```python
"""Integration tests for POST /api/profile/resume/from-story"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_story_endpoint_happy_path(authed_client: AsyncClient):
    """Valid segments → 200 with chunk_count > 0."""
    segments = [
        "I worked at SecureAuth from 2022 to 2025 as a Senior Software Engineer "
        "building anomaly detection systems and ML pipelines for identity security.",
        "Before that I was at Acceptto from 2016 to 2022 building behavioral "
        "authentication systems using Python and Kubernetes.",
    ]
    with patch("app.routers.profile.story_to_resume", new_callable=AsyncMock) as mock_s2r, \
         patch("app.routers.profile.master_crud.create_or_replace_from_text", new_callable=AsyncMock) as mock_crud:

        mock_s2r.return_value = "PROFESSIONAL SUMMARY\nExperienced engineer.\n\nSKILLS\nPython, AWS"
        mock_crud.return_value = (MockResume(), [MockChunk()], True)

        response = await authed_client.post(
            "/api/profile/resume/from-story",
            json={"segments": segments, "whisper_path": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["embedding_warning"] is None


@pytest.mark.asyncio
async def test_story_endpoint_too_few_words(authed_client: AsyncClient):
    """Segments with fewer than 50 words total → 422."""
    response = await authed_client.post(
        "/api/profile/resume/from-story",
        json={"segments": ["Hi", "I worked"], "whisper_path": False},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_story_endpoint_too_many_segments(authed_client: AsyncClient):
    """31 segments → 422."""
    segments = ["I worked at a company for many years and built important systems." * 2] * 31
    response = await authed_client.post(
        "/api/profile/resume/from-story",
        json={"segments": segments, "whisper_path": False},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_story_endpoint_llm_failure(authed_client: AsyncClient):
    """LLM RuntimeError → 502 with story_conversion_failed code."""
    with patch("app.routers.profile.story_to_resume", side_effect=RuntimeError("LLM failed")):
        response = await authed_client.post(
            "/api/profile/resume/from-story",
            json={"segments": ["I worked at SecureAuth for three years building ML infrastructure "
                               "and anomaly detection systems for identity security."],
                  "whisper_path": False},
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "story_conversion_failed"


@pytest.mark.asyncio
async def test_story_endpoint_unauthenticated(client: AsyncClient):
    """No auth header → 401."""
    response = await client.post(
        "/api/profile/resume/from-story",
        json={"segments": ["Some career story text goes here."], "whisper_path": False},
    )
    assert response.status_code == 401
```

**Create / modify:** `backend/tests/unit/test_story_quota.py`

```python
"""Unit tests for story_build quota routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.billing.quota import check_quota_for_story, QuotaAction


@pytest.mark.asyncio
async def test_story_byok_is_free():
    """BYOK users pay 0 credits regardless of browser path."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False)
    result = await check_quota_for_story(
        mock_db, user=mock_user, whisper_path=True, byok_active=True
    )
    assert result.charged_to == "byok"
    assert result.action == QuotaAction.story_build


@pytest.mark.asyncio
async def test_story_web_speech_is_free():
    """Web Speech path costs 0 credits for free users (no subscription)."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False)
    with patch("app.services.billing.quota._active_subscription_for", return_value=None):
        result = await check_quota_for_story(
            mock_db, user=mock_user, whisper_path=False, byok_active=False
        )
    assert result.charged_to == "free_web_speech"


@pytest.mark.asyncio
async def test_story_whisper_costs_two_credits():
    """Whisper path costs 2 credits for free users."""
    mock_db = AsyncMock()
    mock_user = MagicMock(is_suspended=False, id="user-1")
    mock_transaction = MagicMock(id="txn-1")
    with patch("app.services.billing.quota._active_subscription_for", return_value=None), \
         patch("app.services.billing.quota.consume_credit", return_value=mock_transaction) as mock_consume:
        result = await check_quota_for_story(
            mock_db, user=mock_user, whisper_path=True, byok_active=False
        )
    assert result.charged_to == "free_credit"
    # consume_credit called with amount=2
    call_kwargs = mock_consume.call_args
    assert call_kwargs.kwargs.get("amount") == 2 or call_kwargs.args[2] == 2
```

### 3.2 Frontend tests

Create test files at:
- `frontend/tests/components/StoryRecorder.test.tsx`
- `frontend/tests/components/StorySegment.test.tsx`
- `frontend/tests/lib/story.test.ts`
- `frontend/tests/pages/profile.test.tsx` (add story-mode param test)
- `frontend/tests/pages/dashboard.test.tsx` (add story CTA test)
- `frontend/tests/pages/session-new.test.tsx` (add promo card test)

Follow the patterns in existing test files for mocking, rendering, and assertions. Tests should cover the cases listed in §21.9 of the system design doc.

---

## Part 4 — Git Workflow

**Branch:** `feature/story-mode` (cut from `main`)

Commit order (one commit per logical step):

```
feat: add story_to_resume.txt prompt for narrative-to-resume conversion
feat: add agent/story.py — story_to_resume() LLM call
feat: add models/story.py — StoryToResumeRequest with segment validation
feat: add story_build quota action and check_quota_for_story()
feat: add POST /api/profile/resume/from-story endpoint
feat: add lib/story.ts — submitStory() frontend helper
feat: add StorySegment component — editable per-segment block
feat: add StoryRecorder component — segmented voice story UI
feat: add Story tab as default to ProfileUploadZone
feat: add ?mode=story URL param and ?return= redirect to profile page
feat: add story CTA empty state to dashboard
feat: add story promotional card to session wizard
test: add backend unit tests for story_to_resume and quota routing
test: add backend integration tests for /api/profile/resume/from-story
test: add frontend tests for StoryRecorder, StorySegment, story lib
```

**PR title:** `feat: Story Mode — "Tell your story. Get a professional resume."`

**PR must include:**
- All commits above
- `pytest` passing (zero failures, zero regressions in existing tests)
- `next build` passing with zero TypeScript errors
- Docker `docker compose build` succeeds for both services
- Linter passing (`ruff check backend/app`, `npx tsc --noEmit`)
- PR description documents: credit rules, browser compatibility, new endpoint, new components

---

## Acceptance Criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | Chrome user records 3 segments, clicks Generate, sees master resume sections populated | E2E manual |
| 2 | Live transcript appears as user speaks in Chrome | Manual |
| 3 | Segment auto-stops at 60 seconds | Wait 60 s or mock timer |
| 4 | Max 30 segments enforced; "Record next" button disabled at 30 | Manual / unit test |
| 5 | Soft warning shown at 18:00 total | Unit test with mocked timer |
| 6 | Each segment editable after recording | Manual |
| 7 | Re-record replaces only that segment | Unit test |
| 8 | Delete removes segment and re-numbers | Unit test |
| 9 | Firefox user sees "2 credits" disclosure before starting | Manual (or jsdom UA mock) |
| 10 | BYOK user sees "0 credits" regardless of browser | Unit test |
| 11 | `/profile?mode=story` activates Story tab automatically | Frontend test |
| 12 | `/profile?mode=story&return=/session/new` redirects to wizard after save | Frontend test |
| 13 | Dashboard shows story CTA when no master resume; hides it when one exists | Frontend test |
| 14 | Session wizard shows promo card when no master resume | Frontend test |
| 15 | `POST /api/profile/resume/from-story` with 31 segments → 422 | Integration test |
| 16 | `POST /api/profile/resume/from-story` with < 50 words → 422 | Integration test |
| 17 | `POST /api/profile/resume/from-story` LLM failure → 502 `story_conversion_failed` | Integration test |
| 18 | Whisper path: 2 credits deducted from ledger | Integration test |
| 19 | BYOK path: 0 credits deducted | Integration test |
| 20 | `story_to_resume.txt` prompt contains `{narrative}` placeholder | Unit test |
| 21 | `next build` passes, `npx tsc --noEmit` passes | CI |
| 22 | `pytest` passes with no regressions | CI |
