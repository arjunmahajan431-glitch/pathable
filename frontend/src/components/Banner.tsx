import type { HealthResponse, RouteResponse } from '../lib/types';

interface BannerProps {
  health: HealthResponse | null;
  result: RouteResponse | null;
}

export function Banner({ health, result }: BannerProps) {
  const area = result?.area ?? health?.area ?? null;

  if (!area?.is_placeholder) return null;

  return (
    <div className="space-y-2" role="region" aria-label="Data status">
      <div className="rounded-xl border-l-4 border-rose-600 bg-rose-50 px-4 py-3 text-sm text-rose-950 shadow-sm dark:border-rose-400 dark:bg-rose-950/40 dark:text-rose-100">
        <p className="font-semibold">Placeholder mapping area</p>
        <p>
          This build uses <strong>{area.name}</strong>, a placeholder chosen because the
          real mapping area was not supplied. Replace it in <code>config/areas.yaml</code>{' '}
          before treating any result as being about your community.
        </p>
      </div>
    </div>
  );
}
