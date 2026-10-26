import type {
  Coverage,
  Explanation,
  Profile,
  ProfilesResponse,
  Route,
  RouteResponse,
  Segment,
  Sensitivity,
} from '../lib/types';

export const TEST_PROFILE: Profile = {
  name: 'wheelchair',
  label: 'Wheelchair',
  description: 'Stairs excluded. Slope and roughness are priced strongly.',
  steps: 'block',
  soft_grade_up_pct: 5,
  hard_grade_up_pct: 8.33,
  grade_factor_up: 0.25,
  surface_multipliers: { smooth: 1, moderate: 1.35, rough: 2.2, very_rough: 4 },
  kerb_unknown_penalty_m: 100,
  crossing_uncontrolled_penalty_m: 20,
  min_width_m: 1.22,
  unknown_grade_factor: 0.15,
  avoid_unlit: false,
  walking_speed_mps: 0.8,
};

export const PROFILES_RESPONSE: ProfilesResponse = {
  profiles: [
    TEST_PROFILE,
    {
      ...TEST_PROFILE,
      name: 'limited_mobility',
      label: 'Limited mobility / cane / walker',
      description: 'Stairs are penalized but not blocked by default.',
      steps: 'penalize',
      walking_speed_mps: 1.1,
    },
  ],
  parameter_specs: [
    {
      key: 'soft_grade_up_pct',
      label: 'Start penalizing uphill slope above',
      help: 'Below this running grade a slope adds no extra cost.',
      min: 0,
      max: 20,
      step: 0.5,
      unit: '%',
      kind: 'number',
      group: 'Slope',
    },
    {
      key: 'hard_grade_up_pct',
      label: 'Never exceed uphill slope',
      help: 'Routes above this grade are blocked unless your profile allows a penalty.',
      min: 1,
      max: 25,
      step: 0.5,
      unit: '%',
      kind: 'number',
      group: 'Slope',
    },
    {
      key: 'surface_multipliers.very_rough',
      label: 'Cost of very rough surfaces',
      help: 'Multiplier for cobbles, gravel, sand or mud.',
      min: 1,
      max: 8,
      step: 0.1,
      unit: '×',
      kind: 'number',
      group: 'Surface',
    },
    {
      key: 'avoid_unlit',
      label: 'Prefer lit paths',
      help: 'Adds cost to unlit and unknown-lighting segments.',
      min: null,
      max: null,
      step: null,
      unit: '',
      kind: 'boolean',
      group: 'Comfort',
    },
  ],
  risks: ['direct', 'balanced', 'cautious'],
  risk_note: 'Risk scales only the price of unknown data.',
  disclaimer: 'Not medical advice.',
};

export const COVERAGE: Coverage = {
  attributes: {
    steps: {
      label: 'Steps',
      known_length_m: 380,
      total_length_m: 380,
      coverage: 1,
      note: '',
    },
    surface: {
      label: 'Surface type',
      known_length_m: 190,
      total_length_m: 380,
      coverage: 0.5,
      note: '',
    },
    grade: {
      label: 'Slope',
      known_length_m: 380,
      total_length_m: 380,
      coverage: 1,
      note: '',
    },
  },
  overall: 0.833333,
  note: 'Coverage measures mapping completeness, not safety.',
};

export const SEGMENT: Segment = {
  id: 'S:B:0',
  u: 'S',
  v: 'B',
  key: '0',
  street_name: 'Synthetic Street',
  highway: 'footway',
  coords: [
    [-75, 40],
    [-74.999, 40.0005],
  ],
  length_m: 100,
  surface: 'asphalt',
  smoothness: null,
  width_m: 1.5,
  grade_pct: 6,
  is_crossing: false,
  kerb: null,
  provenance: {
    steps: 'OSM_MAPPED',
    surface: 'OSM_MAPPED',
    smoothness: 'UNKNOWN',
    width: 'OSM_MAPPED',
    grade: 'OSM_MAPPED',
    kerb: 'UNKNOWN',
  },
  unknown_attributes: ['smoothness'],
  cost: {
    length_m: 100,
    base_m_eq: 100,
    terms: [
      {
        name: 'grade',
        kind: 'multiplier',
        value: 1.25,
        m_eq: 25,
        reason: '6.0% uphill grade is above the 5.0% soft threshold.',
        provenance: 'OSM_MAPPED',
      },
      {
        name: 'unknown_smoothness',
        kind: 'multiplier',
        value: 1.06,
        m_eq: 7.5,
        reason: 'Smoothness is not mapped; priced as a risk.',
        provenance: 'UNKNOWN',
      },
    ],
    total_m_eq: 132.5,
    hard_block: null,
    profile: 'test_wheelchair',
    risk: 'balanced',
  },
  field_audit: false,
};

export function makeRoute(overrides: Partial<Route> = {}): Route {
  return {
    kind: 'preferred',
    distance_m: 380,
    cost_m_eq: 405,
    estimated_minutes: 7.9,
    speed_mps: 0.8,
    geometry: {
      type: 'LineString',
      coordinates: [
        [-75, 40],
        [-74.999, 40.0005],
      ],
    },
    segments: [SEGMENT],
    barriers: [],
    coverage: COVERAGE,
    is_relaxed: false,
    relaxed_constraints: [],
    ...overrides,
  };
}

export const EXPLANATION: Explanation = {
  summary: 'The preferred route is 380 m, +80 m (+27%) versus the length-only route.',
  why_this_route: ['Slope: +25 m-eq. 6% uphill is above your soft threshold.'],
  why_not_shortest: ['Synthetic Street (50 m): BLOCKED - mapped steps.'],
  what_we_dont_know: ['Clear width is unknown on 40% of the route.'],
  reports: ['No community reports are influencing this route.'],
  assumptions: ['Travel time uses 0.80 m/s, a user-adjustable assumption.'],
  coverage_note: 'Coverage measures mapping completeness, not safety.',
};

export const SENSITIVITY: Sensitivity[] = [
  {
    parameter: 'hard_grade_up_pct',
    label: 'Hard uphill slope limit',
    baseline_value: 8.33,
    unit: '%',
    variants: [
      {
        value: 7.33,
        distance_m: 420,
        cost_m_eq: 500,
        differs_from_baseline: true,
        route_available: true,
        description: 'At 7.3% the route changes.',
      },
      {
        value: 9.33,
        distance_m: 380,
        cost_m_eq: 405,
        differs_from_baseline: false,
        route_available: true,
        description: 'At 9.3% the route is unchanged.',
      },
    ],
    note: 'Only this setting changed.',
  },
];

export function makeResponse(overrides: Partial<RouteResponse> = {}): RouteResponse {
  const shortest = makeRoute({
    kind: 'shortest',
    distance_m: 300,
    cost_m_eq: 300,
    barriers: [
      {
        segment_id: 'S:A:0',
        reason: 'mapped steps (highway=steps)',
        attribute: 'steps',
        provenance: 'OSM_MAPPED',
        street_name: 'Synthetic Street',
        distance_m: 50,
      },
    ],
  });
  return {
    area: {
      id: 'test',
      name: 'Synthetic test area',
      center: { lat: 40.001, lon: -75 },
      radius_m: 1000,
      is_placeholder: false,
      note: '',
    },
    data: {
      source: 'Synthetic test fixture',
      fetched_at: '2026-01-01',
      demo_mode: true,
      demo_reason: 'unit test',
      elevation_source: '',
      elevation_date: '',
      nodes: 7,
      edges: 9,
    },
    profile: TEST_PROFILE,
    risk: 'balanced',
    shortest,
    preferred: makeRoute(),
    relaxed_alternative: null,
    no_feasible_route: null,
    explanation: EXPLANATION,
    sensitivity: SENSITIVITY,
    warnings: [
      { code: 'demo_mode', message: 'Demo data.', severity: 'warning' },
    ],
    snap: { start_distance_m: 0, end_distance_m: 0 },
    request_note: 'Coverage measures mapping, not safety.',
    ...overrides,
  };
}
