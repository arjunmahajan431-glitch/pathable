import { formatMeters } from '../lib/format';
import type { Sensitivity } from '../lib/types';

export function SensitivityView({ sensitivity }: { sensitivity: Sensitivity[] }) {
  if (sensitivity.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby="sensitivity-heading" className="space-y-3">
      <h3 id="sensitivity-heading" className="text-base font-bold text-slate-900 dark:text-slate-100">
        Sensitivity check
      </h3>
      {sensitivity.map((item) => (
        <div key={item.parameter} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            We recomputed the route with only <strong>{item.label}</strong> changed from the
            baseline of <strong>{item.baseline_value.toFixed(1)}{item.unit}</strong>. This is
            a deterministic check, not a prediction.
          </p>
          <ul className="mt-2 space-y-2">
            {item.variants.map((variant) => (
              <li
                key={variant.value}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 dark:bg-slate-800/60 px-2 py-1.5 text-sm"
              >
                <span>
                  At <strong>{variant.value.toFixed(1)}{item.unit}</strong>:{' '}
                  {variant.route_available
                    ? `${formatMeters(variant.distance_m ?? 0)} route`
                    : 'no route under the hard limits'}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                    variant.differs_from_baseline
                      ? 'bg-amber-100 dark:bg-amber-900/50 text-amber-950 dark:text-amber-100'
                      : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300'
                  }`}
                >
                  {variant.differs_from_baseline ? 'Route changes' : 'Same route'}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">{item.note}</p>
        </div>
      ))}
    </section>
  );
}
