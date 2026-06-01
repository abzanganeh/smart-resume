const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function authRequest<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body?.detail
    const message =
      typeof detail === "string"
        ? detail
        : detail?.code ?? JSON.stringify(detail) ?? `HTTP ${res.status}`
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export interface ExportJob {
  id: string
  status: "pending" | "processing" | "ready" | "failed"
  presigned_url: string | null
  presigned_url_expires_at: string | null
  error: string | null
  created_at: string
  completed_at: string | null
}

export interface ExportListItem {
  id: string
  status: string
  presigned_url: string | null
  presigned_url_expires_at: string | null
  created_at: string
  completed_at: string | null
}

export async function startExport(token: string): Promise<{ job_id: string }> {
  return authRequest("/api/account/export", token, { method: "POST" })
}

export async function getExportJob(
  token: string,
  jobId: string,
): Promise<ExportJob> {
  return authRequest(`/api/account/export/${jobId}`, token)
}

export async function listExports(token: string): Promise<ExportListItem[]> {
  return authRequest("/api/account/exports", token)
}

export async function closeAccount(
  token: string,
  cancelSubscription = true,
): Promise<{ ok: boolean; scheduled_delete_at: string }> {
  return authRequest("/api/account/close", token, {
    method: "POST",
    body: JSON.stringify({ cancel_subscription: cancelSubscription }),
  })
}

export async function cancelAccountClosure(
  token: string,
): Promise<{ ok: boolean }> {
  return authRequest("/api/account/close/cancel", token, { method: "POST" })
}

export async function patchDisplayName(
  token: string,
  displayName: string,
): Promise<{ ok: boolean; display_name: string }> {
  return authRequest("/api/account/profile", token, {
    method: "PATCH",
    body: JSON.stringify({ display_name: displayName }),
  })
}

export async function sendEmailVerification(token: string): Promise<void> {
  await authRequest("/api/auth/verify/send", token, { method: "POST" })
}

export function pollExportUntilReady(
  token: string,
  jobId: string,
  intervalMs = 5000,
  maxAttempts = 60,
): { promise: Promise<ExportJob>; cancel: () => void } {
  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const promise = new Promise<ExportJob>((resolve, reject) => {
    let attempts = 0

    const tick = async () => {
      if (cancelled) return
      attempts += 1
      try {
        const job = await getExportJob(token, jobId)
        if (job.status === "ready") {
          resolve(job)
          return
        }
        if (job.status === "failed") {
          reject(new Error(job.error ?? "Export failed"))
          return
        }
        if (attempts >= maxAttempts) {
          reject(new Error("Export timed out"))
          return
        }
        timer = setTimeout(tick, intervalMs)
      } catch (e) {
        reject(e)
      }
    }

    void tick()
  })

  const cancel = () => {
    cancelled = true
    if (timer) clearTimeout(timer)
  }

  return { promise, cancel }
}
