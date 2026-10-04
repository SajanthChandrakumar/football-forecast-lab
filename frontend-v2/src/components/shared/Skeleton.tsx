import { cn } from '../../lib/util'

/** Neutral shimmer block — size it via className. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-surface-2', className)} />
}

/** Day-grouped fixture list placeholder (Dashboard). */
export function FixtureListSkeleton({ days = 2, rowsPerDay = 4 }: { days?: number; rowsPerDay?: number }) {
  return (
    <div className="space-y-7" role="status" aria-label="Spiele werden geladen" aria-busy="true">
      <span className="sr-only">Spiele werden geladen …</span>
      {Array.from({ length: days }, (_, d) => (
        <section key={d}>
          <Skeleton className="mb-2 h-3.5 w-44" />
          <div className="glass overflow-hidden !p-0">
            {Array.from({ length: rowsPerDay }, (_, r) => (
              <div key={r} className="flex items-center gap-4 border-b border-line px-5 py-4 last:border-b-0">
                <Skeleton className="h-4 w-10" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="hidden h-4 w-24 sm:block" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

/** Grid of card stubs (Edge, Value Bets, Groups …). `cols` replaces the default column classes. */
export function CardGridSkeleton({ count = 4, cols = 'md:grid-cols-2' }: { count?: number; cols?: string }) {
  return (
    <div className={cn('grid gap-4', cols)}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="glass space-y-3 p-5">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  )
}

/** Chart-shaped placeholder: title bar + tall plot area. */
export function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('glass p-5', className)}>
      <Skeleton className="mb-4 h-3.5 w-36" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}

/** KPI row + section stubs (Performance). */
export function PerformanceSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="glass p-5">
            <Skeleton className="mb-3 h-3 w-28" />
            <Skeleton className="h-12 w-24" />
          </div>
        ))}
      </div>
      <ChartSkeleton />
      <CardGridSkeleton count={2} />
    </div>
  )
}
