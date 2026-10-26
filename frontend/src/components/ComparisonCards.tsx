import {
  coverageText,
  detourLabel,
  formatMeters,
  formatMinutes,
  formatPercent,
} from '../lib/format';
import type { Route, RouteResponse } from '../lib/types';

function CoverageBar({ value }: { value: number | null }) {
  const pct = value === null ? 0 : Math.round(value * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-600 dark:text-slate-400">
        <span>Data coverage</span>
        <span className="font-semibold text-slate-800 dark:text-slate-200">{coverageText(value)}</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
        role="img"
        aria-label={`Data coverage ${pct} percent. Mapping completeness, not safety.`}
      >
        <div className="h-full rounded-full bg-slate-700" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RouteLine({ variant }: { variant: 'preferred' | 'shortest' | 'relaxed' }) {
  if (variant === 'shortest') {
    return (
      <span
        aria-hidden="true"
        className="inline-block h-1.5 w-9 rounded border-t-4 border-dashed border-amber-700"
      />
    );
  }
  if (variant === 'relaxed') {
    return (
      <span
        aria-hidden="true"
        className="inline-block h-1.5 w-9 rounded border-t-4 border-dashed border-rose-700"
      />
    );
  }
  return <span aria-hidden="true" className="inline-block h-1.5 w-9 rounded bg-blue-700" />;
}

function RouteCard({
  route,
  title,
  variant,
  shortest,
  tone,
}: {
  route: Route;
  title: string;
  variant: 'preferred' | 'shortest' | 'relaxed';
  shortest: Route | null;
  tone: 'blue' | 'amber' | 'rose';
}) {
  const unknownCount = Object.values(route.coverage.attributes).filter(
    (attribute) => attribute.coverage !== null && attribute.coverage < 0.9999,
  ).length;
  const border =
    tone === 'blue' ? 'border-blue-200 dark:border-blue-800' : tone === 'amber' ? 'border-amber-200 dark:border-amber-800' : 'border-rose-200';
  return (
    <article
      className={`relative flex h-full flex-col gap-3 overflow-hidden rounded-2xl border bg-white p-4 shadow-sm dark:bg-slate-900 ${border}`}
      aria-label={`${title} route summary`}
    >
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-0 h-1 ${
          tone === 'blue' ? 'bg-blue-600' : tone === 'amber' ? 'bg-amber-500' : 'bg-rose-500'
        }`}
      />
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <RouteLine variant={variant} />
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
              {title}
            </h3>
          </div>
          <p className="text-4xl font-black tracking-tight tabular-nums text-slate-900 dark:text-slate-100">
            {formatMeters(route.distance_m)}
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {variant === 'preferred'
              ? detourLabel(route.distance_m, shortest?.distance_m ?? null)
              : 'Length only, ignores your profile'}
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Time estimate</dt>
          <dd className="font-semibold text-slate-900 dark:text-slate-100">{formatMinutes(route.estimated_minutes)}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Barriers on this route</dt>
          <dd className="font-semibold text-slate-900 dark:text-slate-100">
            {route.barriers.length === 0 ? 'None known' : `${route.barriers.length} blocked`}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Missing attributes</dt>
          <dd className="font-semibold text-slate-900 dark:text-slate-100">{unknownCount}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Effort score</dt>
          <dd className="font-semibold text-slate-900 dark:text-slate-100">
            {Math.round(route.cost_m_eq).toLocaleString()} m-eq
          </dd>
        </div>
      </dl>

      <p className="rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] leading-relaxed text-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
        <strong className="text-slate-800 dark:text-slate-200">Effort score:</strong>{' '}
        {Math.round(route.cost_m_eq).toLocaleString()} m-eq. 1,000 m-eq is meant to feel
        like 1 km of flat, smooth walking, so a longer route can still have a lower score.
      </p>

      <CoverageBar value={route.coverage.overall} />

      {route.barriers.length > 0 && (
        <p className="rounded-md bg-amber-50 dark:bg-amber-950/40 px-2 py-1.5 text-xs text-amber-950 dark:text-amber-100">
          This route is shown for comparison. It violates your hard settings on the
          highlighted segments.
        </p>
      )}
      {route.is_relaxed && (
        <p className="rounded-md bg-rose-50 dark:bg-rose-950/40 px-2 py-1.5 text-xs text-rose-950 dark:text-rose-100">
          Relaxed alternative: {route.relaxed_constraints.join(', ') || 'one constraint'}{' '}
          allowed. It is not a normal result.
        </p>
      )}
      <p className="mt-auto text-xs text-slate-500 dark:text-slate-400">
        Time assumes {route.speed_mps.toFixed(2)} m/s, which you can change. Coverage is{' '}
        {formatPercent(route.coverage.overall ?? 0)}. It measures how much is mapped, not
        whether the route is safe.
      </p>
    </article>
  );
}

interface ComparisonCardsProps {
  result: RouteResponse;
}

export function ComparisonCards({ result }: ComparisonCardsProps) {
  const { preferred, shortest, relaxed_alternative: relaxed } = result;
  return (
    <section aria-labelledby="comparison-heading" className="space-y-3">
      <div>
        <h2 id="comparison-heading" className="text-xl font-bold text-slate-900 dark:text-slate-100">
          Route comparison
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          The preferred route follows your settings. The shortest route is shown for
          comparison and may be blocked. A lower effort score means the route should feel
          easier, not that it is guaranteed safe.
        </p>
      </div>
      {preferred ? (
        <div className="grid gap-3 md:grid-cols-2">
          <RouteCard
            route={preferred}
            title="Preferred"
            variant="preferred"
            shortest={shortest}
            tone="blue"
          />
          {shortest && (
            <RouteCard
              route={shortest}
              title="Shortest (length only)"
              variant="shortest"
              shortest={shortest}
              tone="amber"
            />
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 p-4 text-sm text-amber-950 dark:text-amber-100">
          <h3 className="font-bold">No route meets your hard limits</h3>
          <p>{result.no_feasible_route?.message}</p>
          {result.no_feasible_route?.blocking_reasons.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {result.no_feasible_route.blocking_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          {relaxed && (
            <div className="mt-3">
              <p className="font-semibold">
                A clearly labeled alternative exists if you allow:{' '}
                {relaxed.relaxed_constraints.join(', ') || 'the blocked constraint'}.
              </p>
              <div className="mt-2">
                <RouteCard
                  route={relaxed}
                  title="Relaxed alternative"
                  variant="relaxed"
                  shortest={shortest}
                  tone="rose"
                />
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
