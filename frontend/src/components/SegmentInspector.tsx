import { attributeLabel, formatMeters, formatPercent, provenanceLabel } from '../lib/format';
import type { Route, Segment } from '../lib/types';

interface SegmentInspectorProps {
  route: Route;
  selectedSegmentId: string | null;
  onSelect: (segmentId: string) => void;
}

function SegmentButton({
  segment,
  index,
  selected,
  onSelect,
}: {
  segment: Segment;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const blocked = segment.cost.hard_block !== null;
  const unknown = segment.unknown_attributes.length > 0;
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={`flex min-h-11 w-full flex-col gap-1 rounded-lg border px-3 py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 ${
          selected
            ? 'border-blue-700 bg-blue-50 dark:bg-blue-950/40'
            : blocked
              ? 'border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-950/40'
              : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800'
        }`}
      >
        <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
          <span className="tabular-nums text-slate-600 dark:text-slate-400">{index + 1}.</span>
          {segment.street_name ?? segment.highway ?? 'Unnamed path'}
          <span className="text-xs font-normal text-slate-600 dark:text-slate-400">
            {formatMeters(segment.length_m)}
          </span>
          {blocked && (
            <span className="rounded-full bg-rose-100 dark:bg-rose-900/50 px-2 py-0.5 text-[11px] font-bold text-rose-900 dark:text-rose-200">
              Blocked by your profile
            </span>
          )}
          {segment.field_audit && (
            <span className="rounded-full bg-emerald-100 dark:bg-emerald-900/50 px-2 py-0.5 text-[11px] font-bold text-emerald-900 dark:text-emerald-200">
              Field audit
            </span>
          )}
          {unknown && (
            <span className="rounded-full border border-dotted border-violet-700 dark:border-violet-400 bg-violet-50 dark:bg-violet-950/40 px-2 py-0.5 text-[11px] font-semibold text-violet-900 dark:text-violet-200">
              Unknown data
            </span>
          )}
        </span>
        <span className="text-xs text-slate-600 dark:text-slate-400">
          {segment.is_crossing ? 'Crossing' : 'Path'} · {segment.cost.total_m_eq.toFixed(0)} m-eq
          {segment.grade_pct !== null ? ` · slope ${segment.grade_pct.toFixed(1)}%` : ' · slope unknown'}
        </span>
      </button>
    </li>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-sm font-medium text-slate-900 dark:text-slate-100">{value}</dd>
    </div>
  );
}

function SelectedSegment({ segment }: { segment: Segment }) {
  return (
    <div
      role="region"
      aria-label="Selected segment details"
      className="mt-4 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/60 p-3"
    >
      <h4 className="text-base font-bold text-slate-900 dark:text-slate-100">
        {segment.street_name ?? segment.highway ?? 'Unnamed path'}
      </h4>
      <p className="mb-2 text-xs text-slate-600 dark:text-slate-400">
        Segment {segment.id}. All values below are copied from the routing graph.
      </p>

      {segment.cost.hard_block && (
        <div role="alert" className="mb-3 rounded-md border border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-950/40 p-2 text-sm text-rose-950 dark:text-rose-100">
          <strong>Blocked:</strong> {segment.cost.hard_block.reason} (
          {provenanceLabel(segment.cost.hard_block.provenance)}).
        </div>
      )}

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Fact label="Length" value={formatMeters(segment.length_m, 1)} />
        <Fact label="Surface" value={segment.surface ?? 'Unknown'} />
        <Fact label="Smoothness" value={segment.smoothness ?? 'Unknown'} />
        <Fact label="Clear width" value={segment.width_m !== null ? `${segment.width_m.toFixed(2)} m` : 'Unknown'} />
        <Fact label="Slope" value={segment.grade_pct !== null ? `${segment.grade_pct.toFixed(1)}%` : 'Unknown'} />
        <Fact
          label={segment.is_crossing ? 'Crossing kerb' : 'Kerb'}
          value={segment.kerb ?? (segment.is_crossing ? 'Unknown' : 'Not a crossing')}
        />
      </dl>

      <h5 className="mb-1 mt-3 text-sm font-bold text-slate-900 dark:text-slate-100">Where each value comes from</h5>
      <ul className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        {Object.entries(segment.provenance).map(([attribute, provenance]) => (
          <li key={attribute} className="flex justify-between gap-2 border-b border-slate-200 dark:border-slate-700 py-1">
            <span className="text-slate-600 dark:text-slate-400">{attributeLabel(attribute)}</span>
            <span
              className={
                provenance === 'UNKNOWN'
                  ? 'font-semibold text-violet-900 dark:text-violet-200'
                  : 'font-semibold text-slate-800 dark:text-slate-200'
              }
            >
              {provenanceLabel(provenance)}
            </span>
          </li>
        ))}
      </ul>

      <h5 className="mb-1 mt-3 text-sm font-bold text-slate-900 dark:text-slate-100">
        How the effort score is built
      </h5>
      <p className="mb-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
        Each term below is measured in meter-equivalents (m-eq). One m-eq means the effort
        of walking 1 m on flat, smooth pavement. A +100 m-eq term feels like walking an
        extra 100 m.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left text-xs">
          <caption className="sr-only">
            Cost terms in meter-equivalents for this segment
          </caption>
          <thead>
            <tr className="border-b border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400">
              <th scope="col" className="py-1 pr-2 font-semibold">Term</th>
              <th scope="col" className="py-1 pr-2 font-semibold">m-eq</th>
              <th scope="col" className="py-1 font-semibold">Reason and provenance</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-slate-200 dark:border-slate-700">
              <td className="py-1 pr-2">Base length</td>
              <td className="py-1 pr-2 tabular-nums">{segment.cost.base_m_eq.toFixed(1)}</td>
              <td className="py-1">Walking distance on an ideal path.</td>
            </tr>
            {segment.cost.terms.map((term) => (
              <tr key={`${term.name}-${term.reason}`} className="border-b border-slate-200 dark:border-slate-700">
                <td className="py-1 pr-2">{term.name.replaceAll('_', ' ')}</td>
                <td className="py-1 pr-2 tabular-nums">+{term.m_eq.toFixed(1)}</td>
                <td className="py-1">
                  {term.reason}{' '}
                  <span className="font-semibold text-slate-600 dark:text-slate-400">
                    [{provenanceLabel(term.provenance)}]
                  </span>
                </td>
              </tr>
            ))}
            <tr>
              <th scope="row" className="py-1 pr-2 font-bold">Total</th>
              <td className="py-1 pr-2 font-bold tabular-nums">{segment.cost.total_m_eq.toFixed(1)}</td>
              <td className="py-1">
                {formatPercent(segment.cost.total_m_eq / Math.max(segment.length_m, 0.001) - 1, 0)}{' '}
                more effort than the plain walking distance.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {segment.unknown_attributes.length > 0 && (
        <p className="mt-2 rounded-md border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/40 p-2 text-xs text-violet-950 dark:text-violet-100">
          Unknown for this profile: {segment.unknown_attributes.map(attributeLabel).join(', ')}.
          Unknown is priced as a risk; it is not treated as safe or as a barrier.
        </p>
      )}
    </div>
  );
}

export function SegmentInspector({ route, selectedSegmentId, onSelect }: SegmentInspectorProps) {
  const selected = route.segments.find((segment) => segment.id === selectedSegmentId) ?? null;
  if (route.segments.length === 0) {
    return (
      <section aria-labelledby="segments-heading" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 id="segments-heading" className="text-lg font-bold text-slate-900 dark:text-slate-100">
          Route segments
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          No travel needed: start and destination snapped to the same pedestrian node.
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="segments-heading" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <h2 id="segments-heading" className="text-lg font-bold text-slate-900 dark:text-slate-100">
        Route segments
      </h2>
      <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
        Text version of the map, for keyboard and screen-reader users. Select a segment to
        inspect its full cost breakdown and provenance.
      </p>
      <ol className="space-y-2">
        {route.segments.map((segment, index) => (
          <SegmentButton
            key={segment.id}
            segment={segment}
            index={index}
            selected={segment.id === selectedSegmentId}
            onSelect={() => onSelect(segment.id)}
          />
        ))}
      </ol>
      {selected ? (
        <SelectedSegment segment={selected} />
      ) : (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">Select a segment above to inspect it.</p>
      )}
    </section>
  );
}
