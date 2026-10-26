import type { Area } from '../lib/types';

interface AreaSwitcherProps {
  areas: Area[];
  activeId: string | null;
  loading: boolean;
  onSwitch: (areaId: string) => void;
}

function shortName(area: Area): string {
  return area.name.replace(/,\s*Minnesota$/i, '');
}

export function AreaSwitcher({ areas, activeId, loading, onSwitch }: AreaSwitcherProps) {
  if (areas.length === 0) return null;
  return (
    <div
      role="group"
      aria-label="Mapping area"
      className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white/90 p-1 shadow-sm dark:border-slate-700 dark:bg-slate-900/90"
    >
      <span className="hidden items-center gap-1 pl-2 pr-1 text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400 sm:inline-flex">
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-3.5 w-3.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M12 21s7-5.1 7-11a7 7 0 1 0-14 0c0 5.9 7 11 7 11Z" strokeLinejoin="round" />
          <circle cx="12" cy="10" r="2.4" />
        </svg>
        Citywide
      </span>
      {areas.map((area) => {
        const active = area.id === activeId;
        return (
          <button
            key={area.id}
            type="button"
            aria-pressed={active}
            disabled={loading}
            onClick={() => onSwitch(area.id)}
            title={`Map ${shortName(area)}`}
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait ${
              active
                ? 'bg-blue-800 text-white shadow-sm dark:bg-blue-500 dark:text-slate-950'
                : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
            }`}
          >
            {loading && active ? (
              <span
                aria-hidden="true"
                className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
              />
            ) : null}
            {shortName(area)}
          </button>
        );
      })}
    </div>
  );
}
