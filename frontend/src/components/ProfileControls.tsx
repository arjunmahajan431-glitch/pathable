import { getParam, riskLabel, setParam } from '../lib/format';
import type { ParameterSpec, Profile, Risk } from '../lib/types';

interface ProfileControlsProps {
  profiles: Profile[];
  selectedName: string;
  profile: Profile;
  specs: ParameterSpec[];
  risk: Risk;
  disabled: boolean;
  onProfileSelect: (name: string) => void;
  onProfileChange: (profile: Profile) => void;
  onRiskChange: (risk: Risk) => void;
  onReset: () => void;
}

const RISK_COPY: Record<Risk, string> = {
  direct: 'Missing data adds a small amount of effort. Routes may use more gaps.',
  balanced: 'Missing data adds a moderate amount of effort. A middle setting.',
  cautious: 'Missing data adds a lot of effort. Routes may be longer to stay on mapped paths.',
};

const PAIRED_LIMITS: Record<string, { minFrom?: keyof Profile; maxFrom?: keyof Profile }> = {
  soft_grade_up_pct: { maxFrom: 'hard_grade_up_pct' },
  hard_grade_up_pct: { minFrom: 'soft_grade_up_pct' },
  soft_grade_down_pct: { maxFrom: 'hard_grade_down_pct' },
  hard_grade_down_pct: { minFrom: 'soft_grade_down_pct' },
};

function ParameterControl({
  spec,
  profile,
  onChange,
}: {
  spec: ParameterSpec;
  profile: Profile;
  onChange: (profile: Profile) => void;
}) {
  const value = getParam(profile, spec.key);
  const id = `param-${spec.key.replaceAll('.', '-')}`;
  if (spec.kind === 'boolean') {
    return (
      <div className="flex items-start gap-2 py-1">
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(setParam(profile, spec.key, event.target.checked))}
          className="mt-1 h-5 w-5 rounded border-slate-400 text-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:border-slate-500 dark:bg-slate-900 dark:accent-blue-400"
        />
        <div>
          <label htmlFor={id} className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {spec.label}
          </label>
          <p id={`${id}-help`} className="text-xs text-slate-600 dark:text-slate-400">
            {spec.help}
          </p>
        </div>
      </div>
    );
  }

  const paired = PAIRED_LIMITS[spec.key];
  let min = spec.min ?? 0;
  let max = spec.max ?? 1;
  if (paired?.minFrom) min = Math.max(min, Number(profile[paired.minFrom]));
  if (paired?.maxFrom) max = Math.min(max, Number(profile[paired.maxFrom]));
  max = Math.max(min, max);

  const numeric = Number(value);
  const clamp = (next: number) => Math.min(max, Math.max(min, next));
  return (
    <div className="py-1">
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium text-slate-800 dark:text-slate-200">
          {spec.label}
        </label>
        <output htmlFor={id} className="text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-300">
          {numeric.toFixed(spec.step && spec.step < 0.1 ? 2 : 1)} {spec.unit}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={spec.step ?? 0.1}
        value={numeric}
        aria-describedby={`${id}-help`}
        onChange={(event) =>
          onChange(setParam(profile, spec.key, clamp(Number(event.target.value))))
        }
        className="mt-1 h-6 w-full accent-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:accent-blue-400"
      />
      <p id={`${id}-help`} className="text-xs leading-snug text-slate-600 dark:text-slate-400">
        {spec.help}
      </p>
    </div>
  );
}

export function ProfileControls({
  profiles,
  selectedName,
  profile,
  specs,
  risk,
  disabled,
  onProfileSelect,
  onProfileChange,
  onRiskChange,
  onReset,
}: ProfileControlsProps) {
  const groups = [...new Set(specs.map((spec) => spec.group))];
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="profile-select" className="block text-sm font-bold text-slate-900 dark:text-slate-100">
          Mobility profile
        </label>
        <select
          id="profile-select"
          value={selectedName}
          disabled={disabled}
          onChange={(event) => onProfileSelect(event.target.value)}
          className="mt-1 min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 text-sm text-slate-900 dark:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          {profiles.map((item) => (
            <option key={item.name} value={item.name}>
              {item.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{profile.description}</p>
      </div>

      <fieldset className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
        <legend className="px-1 text-sm font-bold text-slate-900 dark:text-slate-100">Risk setting</legend>
        <div className="space-y-2">
          {(['direct', 'balanced', 'cautious'] as Risk[]).map((option) => (
            <label key={option} className="flex min-h-11 items-start gap-2 text-sm">
              <input
                type="radio"
                name="risk"
                value={option}
                checked={risk === option}
                onChange={() => onRiskChange(option)}
                className="mt-1 h-5 w-5 border-slate-400 text-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:border-slate-500 dark:bg-slate-900 dark:accent-blue-400"
              />
              <span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">{riskLabel(option)}</span>
                <span className="block text-xs text-slate-600 dark:text-slate-400">{RISK_COPY[option]}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Fine-tune the route</h3>
        <button
          type="button"
          onClick={onReset}
          className="min-h-11 rounded-md px-2 text-xs font-semibold text-blue-800 dark:text-blue-300 underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          Reset profile
        </button>
      </div>

      <details className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/60">
        <summary className="cursor-pointer text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:text-slate-200">
          What do these numbers mean?
        </summary>
        <ul className="mt-2 space-y-2 text-xs leading-relaxed text-slate-700 dark:text-slate-300">
          <li>
            <strong className="text-slate-900 dark:text-slate-100">Slope:</strong> a 5%
            slope rises 5 cm for every 1 m forward. 8.3% is about 1 m of rise over 12 m.
            That is a ramp design reference, not a universal sidewalk limit.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-slate-100">
              Effort score (m-eq):
            </strong>{' '}
            100 m-eq feels like walking an extra 100 m on flat, smooth pavement. A 1,200
            m-eq route may be shorter than a 1,000 m-eq route, but it is expected to feel
            harder.
          </li>
          <li>
            <strong className="text-slate-900 dark:text-slate-100">Missing data:</strong>{' '}
            “Unknown” means no mapped value. It is not treated as safe and it is not a
            barrier. The risk setting decides how much extra effort we add.
          </li>
        </ul>
      </details>

      {groups.map((group, index) => (
        <details key={group} open={index === 0} className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800 dark:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700">
            {group}
          </summary>
          <div className="mt-2 space-y-2">
            {specs
              .filter((spec) => spec.group === group)
              .map((spec) => (
                <ParameterControl
                  key={spec.key}
                  spec={spec}
                  profile={profile}
                  onChange={onProfileChange}
                />
              ))}
          </div>
        </details>
      ))}
    </div>
  );
}
