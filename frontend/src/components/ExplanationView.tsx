import { coverageText, formatPercent } from '../lib/format';
import type { Coverage, Explanation, Warning } from '../lib/types';
import { SensitivityView } from './SensitivityView';

function ListSection({
  id,
  title,
  items,
  open = false,
}: {
  id: string;
  title: string;
  items: string[];
  open?: boolean;
}) {
  return (
    <details open={open} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
      <summary className="min-h-11 cursor-pointer px-3 py-2 text-sm font-bold text-slate-900 dark:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700">
        {title}
      </summary>
      <ul id={id} className="list-disc space-y-1 px-6 pb-3 text-sm text-slate-700 dark:text-slate-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  );
}

function CoverageView({ coverage }: { coverage: Coverage }) {
  return (
    <details className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
      <summary className="min-h-11 cursor-pointer px-3 py-2 text-sm font-bold text-slate-900 dark:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700">
        Data coverage by attribute ({coverageText(coverage.overall)} overall)
      </summary>
      <div className="px-3 pb-3">
        <ul className="space-y-2">
          {Object.entries(coverage.attributes).map(([key, item]) => {
            const pct = item.coverage === null ? 0 : item.coverage * 100;
            return (
              <li key={key}>
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-700 dark:text-slate-300">{item.label}</span>
                  <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                    {item.coverage === null ? 'n/a' : formatPercent(item.coverage)}
                  </span>
                </div>
                <div
                  className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
                  role="img"
                  aria-label={`${item.label} coverage ${Math.round(pct)} percent`}
                >
                  <div className="h-full rounded-full bg-slate-700" style={{ width: `${pct}%` }} />
                </div>
                {item.note ? <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{item.note}</p> : null}
              </li>
            );
          })}
        </ul>
        <p className="mt-3 rounded-md bg-amber-50 dark:bg-amber-950/40 p-2 text-xs text-amber-950 dark:text-amber-100">{coverage.note}</p>
      </div>
    </details>
  );
}

function WarningsView({ warnings }: { warnings: Warning[] }) {
  if (warnings.length === 0) return null;
  return (
    <section aria-labelledby="warnings-heading" className="space-y-2">
      <h3 id="warnings-heading" className="text-base font-bold text-slate-900 dark:text-slate-100">
        Warnings and data notes
      </h3>
      <ul className="space-y-2">
        {warnings.map((warning) => (
          <li
            key={`${warning.code}-${warning.message}`}
            className={`rounded-lg border px-3 py-2 text-sm ${
              warning.severity === 'info'
                ? 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300'
                : 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 text-amber-950 dark:text-amber-100'
            }`}
          >
            <strong className="uppercase tracking-wide">{warning.code.replaceAll('_', ' ')}:</strong>{' '}
            {warning.message}
          </li>
        ))}
      </ul>
    </section>
  );
}

interface ExplanationViewProps {
  explanation: Explanation;
  coverage: Coverage;
  warnings: Warning[];
  sensitivity: Parameters<typeof SensitivityView>[0]['sensitivity'];
}

export function ExplanationView({
  explanation,
  coverage,
  warnings,
  sensitivity,
}: ExplanationViewProps) {
  return (
    <section aria-labelledby="explanation-heading" className="space-y-3">
      <div>
        <h2 id="explanation-heading" className="text-lg font-bold text-slate-900 dark:text-slate-100">
          Route explanation
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Plain-language explanations generated deterministically from the cost breakdown.
          Everything is computed locally; no external service is called.
        </p>
      </div>

      <p className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40 p-3 text-sm font-medium text-blue-950 dark:text-blue-100">
        {explanation.summary}
      </p>

      <ListSection
        id="why-route"
        title="Why this route"
        items={explanation.why_this_route}
        open
      />
      <ListSection
        id="why-not-shortest"
        title="Why not the shortest route"
        items={explanation.why_not_shortest}
      />
      <ListSection
        id="what-unknown"
        title="What we don't know"
        items={explanation.what_we_dont_know}
      />
      <ListSection id="reports" title="Reports near this route" items={explanation.reports} />
      <CoverageView coverage={coverage} />
      <SensitivityView sensitivity={sensitivity} />
      <ListSection
        id="assumptions"
        title="Assumptions and limits of this result"
        items={explanation.assumptions}
      />
      <WarningsView warnings={warnings} />
    </section>
  );
}
