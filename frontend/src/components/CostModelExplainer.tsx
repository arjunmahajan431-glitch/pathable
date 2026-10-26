const ROWS = [
  {
    term: 'Distance',
    plain: '100 m of flat, smooth pavement scores 100 m-eq.',
  },
  {
    term: 'Slope',
    plain:
      'A 5% slope rises 5 cm for every 1 m you walk. A gentle rise adds a little effort; a steep one adds a lot, and the wheelchair profile can block it.',
  },
  {
    term: 'Surface, width, crossings',
    plain:
      'Rough ground, a narrow path, a missing curb ramp, or a crossing without a signal adds extra meters to the score.',
  },
  {
    term: 'Unknown data',
    plain:
      'If a value is missing, the score adds a risk price instead of calling it safe. Direct adds one third of that price, Balanced adds the full price, and Cautious adds 2.67 times the price.',
  },
];

export function CostModelExplainer() {
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-sm font-bold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:text-slate-100">
        <span className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="grid h-7 w-7 place-items-center rounded-lg bg-blue-50 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 19h16M7 16V9M12 16V5M17 16v-4" strokeLinecap="round" />
            </svg>
          </span>
          How the effort score works
        </span>
        <span className="text-xs font-medium text-blue-800 group-open:hidden dark:text-blue-300">
          Open
        </span>
        <span className="hidden text-xs font-medium text-blue-800 group-open:inline dark:text-blue-300">
          Close
        </span>
      </summary>
      <div className="mt-3 space-y-3 text-sm text-slate-700 dark:text-slate-300">
        <p>
          PathAble compares routes with one number called an <strong>effort score</strong>. It
          is measured in <strong>meter-equivalents (m-eq)</strong>. One thousand m-eq is meant to
          feel like walking 1 km on flat, smooth pavement, so a longer route can still score
          lower than a shorter one.
        </p>
        <dl className="space-y-2">
          {ROWS.map((row) => (
            <div
              key={row.term}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800/60"
            >
              <dt className="font-semibold text-slate-900 dark:text-slate-100">{row.term}</dt>
              <dd className="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                {row.plain}
              </dd>
            </div>
          ))}
        </dl>
        <p className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs leading-relaxed text-blue-950 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-100">
          <strong>Example:</strong> a 1,000 m route with a 6% uphill and an unknown curb ramp
          might score 1,250 m-eq. That means about 250 m of extra effort, not 250 m of extra
          distance. The score is a comparison tool, not a safety rating or a promise of
          accessibility.
        </p>
      </div>
    </details>
  );
}
