import type { ParameterSpec, Point, Profile, ProfilesResponse, Risk } from '../lib/types';
import { CostModelExplainer } from './CostModelExplainer';
import { PointInput } from './PointInput';
import { ProfileControls } from './ProfileControls';

interface PlanningPanelProps {
  profiles: ProfilesResponse | null;
  selectedName: string;
  profile: Profile | null;
  risk: Risk;
  start: Point | null;
  end: Point | null;
  pointMode: 'start' | 'end';
  loading: boolean;
  onProfileSelect: (name: string) => void;
  onProfileChange: (profile: Profile) => void;
  onRiskChange: (risk: Risk) => void;
  onResetProfile: () => void;
  onStartChange: (point: Point | null) => void;
  onEndChange: (point: Point | null) => void;
  onActivateMap: (which: 'start' | 'end') => void;
  onPlan: () => void;
}

export function PlanningPanel({
  profiles,
  selectedName,
  profile,
  risk,
  start,
  end,
  pointMode,
  loading,
  onProfileSelect,
  onProfileChange,
  onRiskChange,
  onResetProfile,
  onStartChange,
  onEndChange,
  onActivateMap,
  onPlan,
}: PlanningPanelProps) {
  const ready = Boolean(start && end && profile && profiles);
  const specs: ParameterSpec[] = profiles?.parameter_specs ?? [];
  return (
    <div className="space-y-4">
      <section aria-labelledby="trip-heading" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <h2 id="trip-heading" className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Plan a trip
            </h2>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              We do not store your start or destination.
            </p>
          </div>
          <button
            type="button"
            className="min-h-11 rounded-md border border-slate-300 dark:border-slate-600 px-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
            onClick={() => {
              const previousStart = start;
              onStartChange(end);
              onEndChange(previousStart);
            }}
            disabled={!start && !end}
          >
            Swap
          </button>
        </div>

        <div className="space-y-3">
          <PointInput
            which="start"
            title="Start"
            point={start}
            mapActive={pointMode === 'start'}
            onPointChange={onStartChange}
            onActivateMap={() => onActivateMap('start')}
          />
          <PointInput
            which="end"
            title="Destination"
            point={end}
            mapActive={pointMode === 'end'}
            onPointChange={onEndChange}
            onActivateMap={() => onActivateMap('end')}
          />
        </div>

        <button
          type="button"
          onClick={onPlan}
          disabled={!ready || loading}
          className="mt-4 min-h-12 w-full rounded-lg bg-blue-800 px-4 text-base font-bold text-white shadow-sm transition-colors hover:bg-blue-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
        >
          {loading ? 'Finding routes…' : 'Find routes'}
        </button>
        {!start || !end ? (
          <p className="mt-2 text-center text-xs text-slate-600 dark:text-slate-400">
            Set both a start and a destination to continue.
          </p>
        ) : null}
      </section>

      {profile && profiles ? (
        <>
          <section aria-labelledby="settings-heading" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <h2 id="settings-heading" className="mb-1 text-lg font-bold text-slate-900 dark:text-slate-100">
              Make the route fit you
            </h2>
            <p className="mb-3 text-xs text-slate-600 dark:text-slate-400">
              Change how much slope, rough ground, crossings, and missing data count. These
              settings do not change what the map actually says.
            </p>
            <ProfileControls
              profiles={profiles.profiles}
              selectedName={selectedName}
              profile={profile}
              specs={specs}
              risk={risk}
              disabled={false}
              onProfileSelect={onProfileSelect}
              onProfileChange={onProfileChange}
              onRiskChange={onRiskChange}
              onReset={onResetProfile}
            />
          </section>
          <CostModelExplainer />
        </>
      ) : null}
    </div>
  );
}
