export type Risk = 'direct' | 'balanced' | 'cautious';
export type Provenance =
  | 'FIELD_AUDIT'
  | 'OSM_MAPPED'
  | 'COMMUNITY_REPORT'
  | 'DEM_ESTIMATED'
  | 'UNKNOWN';

export interface Point {
  lat: number;
  lon: number;
}

export interface Warning {
  code: string;
  message: string;
  severity: 'info' | 'warning' | 'error';
}

export type AreaBoundary =
  | { type: 'Polygon'; coordinates: [number, number][][] }
  | { type: 'MultiPolygon'; coordinates: [number, number][][][] };

export interface Area {
  id: string;
  name: string;
  center: Point;
  radius_m: number;
  is_placeholder: boolean;
  note: string;
  boundary?: AreaBoundary | null;
  bbox?: [number, number, number, number] | null;
}

export interface DataInfo {
  source: string;
  fetched_at: string;
  demo_mode: boolean;
  demo_reason: string;
  elevation_source: string;
  elevation_date: string;
  nodes: number;
  edges: number;
}

export interface CostTerm {
  name: string;
  kind: 'multiplier' | 'penalty';
  value: number;
  m_eq: number;
  reason: string;
  provenance: Provenance;
}

export interface HardBlock {
  reason: string;
  attribute: string;
  provenance: Provenance;
}

export interface CostBreakdown {
  length_m: number;
  base_m_eq: number;
  terms: CostTerm[];
  total_m_eq: number;
  hard_block: HardBlock | null;
  profile: string;
  risk: Risk;
}

export interface AttributeCoverage {
  label: string;
  known_length_m: number;
  total_length_m: number;
  coverage: number | null;
  note: string;
}

export interface Coverage {
  attributes: Record<string, AttributeCoverage>;
  overall: number | null;
  note: string;
}

export interface Barrier {
  segment_id: string;
  reason: string;
  attribute: string;
  provenance: Provenance;
  street_name: string | null;
  distance_m: number;
}

export interface Segment {
  id: string;
  u: string;
  v: string;
  key: string;
  street_name: string | null;
  highway: string | null;
  coords: [number, number][];
  length_m: number;
  surface: string | null;
  smoothness: string | null;
  width_m: number | null;
  grade_pct: number | null;
  is_crossing: boolean;
  kerb: string | null;
  provenance: Record<string, Provenance>;
  unknown_attributes: string[];
  cost: CostBreakdown;
  field_audit: boolean;
}

export interface Route {
  kind: 'shortest' | 'preferred' | 'relaxed';
  distance_m: number;
  cost_m_eq: number;
  estimated_minutes: number;
  speed_mps: number;
  geometry: { type: 'LineString'; coordinates: [number, number][] };
  segments: Segment[];
  barriers: Barrier[];
  coverage: Coverage;
  is_relaxed: boolean;
  relaxed_constraints: string[];
}

export interface Explanation {
  summary: string;
  why_this_route: string[];
  why_not_shortest: string[];
  what_we_dont_know: string[];
  reports: string[];
  assumptions: string[];
  coverage_note: string;
}

export interface SensitivityVariant {
  value: number;
  distance_m: number | null;
  cost_m_eq: number | null;
  differs_from_baseline: boolean;
  route_available: boolean;
  description: string;
}

export interface Sensitivity {
  parameter: string;
  label: string;
  baseline_value: number;
  unit: string;
  variants: SensitivityVariant[];
  note: string;
}

export interface NoFeasibleRoute {
  code: 'disconnected' | 'hard_constraints';
  message: string;
  blocking_reasons: string[];
  shortest_route_available: boolean;
  relaxed_alternative_available: boolean;
}

export interface RouteResponse {
  area: Area;
  data: DataInfo;
  profile: Profile;
  risk: Risk;
  shortest: Route | null;
  preferred: Route | null;
  relaxed_alternative: Route | null;
  no_feasible_route: NoFeasibleRoute | null;
  explanation: Explanation | null;
  sensitivity: Sensitivity[];
  warnings: Warning[];
  snap: { start_distance_m: number; end_distance_m: number };
  request_note: string;
}

export interface Profile {
  [key: string]: unknown;
  name: string;
  label: string;
  description: string;
  soft_grade_up_pct: number;
  hard_grade_up_pct: number;
  grade_factor_up: number;
  surface_multipliers: Record<string, number>;
  kerb_unknown_penalty_m: number;
  crossing_uncontrolled_penalty_m: number;
  min_width_m: number;
  unknown_grade_factor: number;
  avoid_unlit: boolean;
  walking_speed_mps: number;
}

export interface ParameterSpec {
  key: string;
  label: string;
  help: string;
  min: number | null;
  max: number | null;
  step: number | null;
  unit: string;
  kind: 'number' | 'boolean';
  group: string;
}

export interface ProfilesResponse {
  profiles: Profile[];
  parameter_specs: ParameterSpec[];
  risks: Risk[];
  risk_note: string;
  disclaimer: string;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  graph_loaded: boolean;
  area: Area | null;
  areas: Area[];
  data_date: string | null;
  source: string | null;
  demo_mode: boolean;
  nodes: number;
  edges: number;
  reports_database: string;
  profiles: string[];
  field_audits: number;
  admin_token_configured: boolean;
  graph_error: string | null;
  warnings: Warning[];
}

export interface GeocodeResult {
  display_name: string;
  lat: number;
  lon: number;
  category: string;
}

export interface GeocodeResponse {
  results: GeocodeResult[];
  attribution: string;
  cached: boolean;
}

export interface Report {
  id: number;
  lat: number;
  lon: number;
  category: string;
  description: string;
  created_at: string;
  status: 'unverified' | 'reviewed' | 'resolved' | 'rejected';
  reviewed_at: string | null;
  last_confirmed_at: string | null;
  influence: boolean;
}

export interface ReportCreateResponse {
  id: number;
  status: string;
  message: string;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(
    message: string,
    options: { code?: string; status?: number; details?: Record<string, unknown> } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = options.code ?? 'unknown';
    this.status = options.status ?? 0;
    this.details = options.details ?? {};
  }
}
