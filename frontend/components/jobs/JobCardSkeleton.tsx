export function JobCardSkeleton() {
  return (
    <div
      data-testid="job-card-skeleton"
      className="rounded-xl border border-slate-800 bg-slate-900 p-5 animate-pulse"
    >
      <div className="flex gap-4">
        <div className="w-12 h-12 rounded-lg bg-slate-800 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-slate-800 rounded w-2/3" />
          <div className="h-3 bg-slate-800 rounded w-1/3" />
          <div className="h-3 bg-slate-800 rounded w-1/2" />
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <div className="h-8 bg-slate-800 rounded-lg w-24" />
        <div className="h-8 bg-slate-800 rounded-lg w-28" />
        <div className="h-8 bg-slate-800 rounded-lg w-16" />
      </div>
    </div>
  )
}
