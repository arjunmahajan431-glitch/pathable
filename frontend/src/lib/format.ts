import type { Profile, Provenance, Risk } from './types';

export function formatMeters(value: number, digits = 0): string {
  return `${value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })} m`;
}

export function formatMinutes(value: number): string {
  if (value < 1) return 'under 1 min';
  return `${value.toFixed(value < 10 ? 1 : 0)} min`;
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatCoord(value: number): string {
  return value.toFixed(6);
}

export function riskLabel(risk: Risk): string {
  if (risk === 'direct') return 'Direct - accept more unknown';
  if (risk === 'cautious') return 'Cautious - pay more for unknowns';
  return 'Balanced';
}

export function provenanceLabel(provenance: Provenance | string): string {
  switch (provenance) {
    case 'FIELD_AUDIT':
      return 'Field audit';
    case 'OSM_MAPPED':
      return 'OSM mapped';
    case 'COMMUNITY_REPORT':
      return 'Community report';
    case 'DEM_ESTIMATED':
      return 'DEM estimate';
    default:
      return 'Unknown';
  }
}

export function attributeLabel(attribute: string): string {
  const labels: Record<string, string> = {
    steps: 'Steps',
    surface: 'Surface',
    smoothness: 'Smoothness',
    width: 'Clear width',
    grade: 'Slope',
    kerb: 'Crossing kerb',
    lit: 'Lighting',
    crossing: 'Crossing type',
    access: 'Access',
    barrier: 'Barrier',
  };
  return labels[attribute] ?? attribute.replaceAll('_', ' ');
}

export function getParam(profile: Profile, key: string): number | boolean {
  if (key.includes('.')) {
    const [head, tail] = key.split('.');
    const nested = profile[head];
    if (nested && typeof nested === 'object') {
      const value = (nested as Record<string, unknown>)[tail];
      if (typeof value === 'number' || typeof value === 'boolean') return value;
    }
    return 0;
  }
  const value = profile[key];
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  return 0;
}

export function setParam(profile: Profile, key: string, value: number | boolean): Profile {
  if (key.includes('.')) {
    const [head, tail] = key.split('.');
    const current = profile[head];
    const nested = typeof current === 'object' && current !== null ? { ...current } : {};
    return {
      ...profile,
      [head]: { ...nested, [tail]: value },
    } as Profile;
  }
  return { ...profile, [key]: value };
}

export function detourLabel(distance: number, shortest: number | null): string {
  if (!shortest || shortest <= 0) return 'No comparison';
  const delta = distance - shortest;
  if (Math.abs(delta) < 0.5) return 'Same distance as shortest';
  const pct = (delta / shortest) * 100;
  return `${delta > 0 ? '+' : ''}${delta.toFixed(0)} m (${pct > 0 ? '+' : ''}${pct.toFixed(0)}%) vs shortest`;
}

export function coverageText(value: number | null): string {
  if (value === null) return 'not available';
  return `${(value * 100).toFixed(0)}% mapped`;
}
