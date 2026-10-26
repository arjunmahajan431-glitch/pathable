import { useCallback, useEffect, useMemo, useState } from 'react';

import type { Route } from '../lib/types';

interface Playback {
  playing: boolean;
  progress: number;
  point: [number, number] | null;
  durationSeconds: number;
  toggle: () => void;
  restart: () => void;
}

const MIN_DURATION_MS = 4500;
const MAX_DURATION_MS = 9000;

function cumulativeLengths(coords: [number, number][]): number[] {
  const totals = [0];
  for (let index = 1; index < coords.length; index += 1) {
    const [lat1, lon1] = coords[index - 1] as [number, number];
    const [lat2, lon2] = coords[index] as [number, number];
    const meanLat = ((lat1 + lat2) / 2) * (Math.PI / 180);
    const dy = (lat2 - lat1) * 111_320;
    const dx = (lon2 - lon1) * 111_320 * Math.cos(meanLat);
    totals.push((totals[index - 1] ?? 0) + Math.hypot(dx, dy));
  }
  return totals;
}

function pointAt(coords: [number, number][], totals: number[], fraction: number): [number, number] | null {
  if (coords.length === 0) return null;
  if (coords.length === 1) return coords[0] ?? null;
  const total = totals[totals.length - 1] ?? 0;
  if (total <= 0) return coords[0] ?? null;
  const target = Math.max(0, Math.min(1, fraction)) * total;
  let index = 1;
  while (index < totals.length && (totals[index] ?? 0) < target) index += 1;
  const before = coords[index - 1] ?? coords[0];
  const after = coords[index] ?? coords[coords.length - 1];
  if (!before || !after) return null;
  const start = totals[index - 1] ?? 0;
  const end = totals[index] ?? start;
  const local = end > start ? (target - start) / (end - start) : 0;
  return [before[0] + (after[0] - before[0]) * local, before[1] + (after[1] - before[1]) * local];
}

/**
 * Animates a dot along the preferred route. The caller decides whether motion
 * is allowed; reduced-motion users still get the full static route.
 */
export function useRoutePlayback(route: Route | null, motionAllowed: boolean): Playback {
  const coords = useMemo<[number, number][]>(
    () => (route?.geometry.coordinates ?? []).map(([lon, lat]) => [lat, lon]),
    [route],
  );
  const totals = useMemo(() => cumulativeLengths(coords), [coords]);
  const totalMeters = totals[totals.length - 1] ?? 0;
  const durationMs = Math.max(
    MIN_DURATION_MS,
    Math.min(MAX_DURATION_MS, (totalMeters / 180) * 1000),
  );

  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    setPlaying(false);
    setProgress(0);
  }, [route?.kind, route?.geometry, route?.distance_m]);

  const restart = useCallback(() => {
    if (!motionAllowed || coords.length < 2) return;
    setProgress(0);
    setPlaying(true);
  }, [coords.length, motionAllowed]);

  const toggle = useCallback(() => {
    if (!motionAllowed || coords.length < 2) return;
    if (playing) {
      setPlaying(false);
      return;
    }
    if (progress >= 0.999) setProgress(0);
    setPlaying(true);
  }, [coords.length, motionAllowed, playing, progress]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const start = performance.now() - progress * durationMs;
    const tick = (now: number) => {
      const fraction = Math.min(1, Math.max(0, (now - start) / durationMs));
      setProgress(fraction);
      if (fraction < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        setPlaying(false);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // progress is intentionally not a dependency: it is the animated value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, durationMs]);

  const point = useMemo(() => pointAt(coords, totals, progress), [coords, totals, progress]);

  return {
    playing,
    progress,
    point,
    durationSeconds: Math.round(durationMs / 100) / 10,
    toggle,
    restart,
  };
}
