interface LegendProps {
  compact?: boolean;
}

function SolidSwatch({ className }: { className: string }) {
  return <span aria-hidden="true" className={`inline-block h-1.5 w-8 rounded ${className}`} />;
}

export function Legend({ compact = false }: LegendProps) {
  return (
    <div
      className={`${compact ? 'rounded-lg border border-slate-200/80 bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur dark:border-slate-700 dark:bg-slate-900/95' : 'rounded-2xl border border-slate-200 bg-white p-3 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-900'} text-slate-700 dark:text-slate-300`}
      aria-label="Map legend"
    >
      <p className="mb-2 font-semibold text-slate-900 dark:text-slate-100">Route lines</p>
      <ul className={`${compact ? 'flex flex-wrap gap-x-4 gap-y-1' : 'space-y-2'}`}>
        <li className="flex items-center gap-2">
          <SolidSwatch className="bg-blue-700 dark:bg-blue-400" />
          <span>Preferred: solid blue</span>
        </li>
        <li className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-8 rounded border-t-4 border-dashed border-amber-700 dark:border-amber-400"
          />
          <span>Shortest: dashed amber</span>
        </li>
        <li className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-8 rounded border-t-4 border-dotted border-violet-700 dark:border-violet-400"
          />
          <span>Unknown data: dotted violet</span>
        </li>
        <li className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-8 rounded border-t-2 border-dashed border-slate-500 dark:border-slate-400"
          />
          <span>City limit: dashed gray</span>
        </li>
      </ul>
      <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
        Line style and labels, not color alone, identify each route. Unknown segments are
        unknown, not safe.
      </p>
      <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
        Map data ©{' '}
        <a
          className="underline decoration-slate-400 underline-offset-2 hover:text-slate-900"
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          OpenStreetMap contributors
        </a>
        . Public OSM tiles are for light/demo use; see the README for production tile options.
      </p>
    </div>
  );
}
