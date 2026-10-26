import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ComparisonCards } from './ComparisonCards';
import { makeResponse, makeRoute } from '../test/fixtures';

describe('ComparisonCards', () => {
  it('shows both routes with detour, barriers and coverage', () => {
    render(<ComparisonCards result={makeResponse()} />);
    expect(screen.getByRole('heading', { name: 'Preferred' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Shortest (length only)' })).toBeInTheDocument();
    expect(screen.getByText('380 m')).toBeInTheDocument();
    expect(screen.getByText('+80 m (+27%) vs shortest')).toBeInTheDocument();
    expect(screen.getByText('1 blocked')).toBeInTheDocument();
    expect(screen.getAllByText(/mapped/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Time assumes 0.80 m\/s/).length).toBeGreaterThan(0);
  });

  it('explains a hard-constraint failure and labels a relaxed alternative', () => {
    const relaxed = makeRoute({
      kind: 'relaxed',
      distance_m: 300,
      is_relaxed: true,
      relaxed_constraints: ['steps'],
    });
    render(
      <ComparisonCards
        result={makeResponse({
          preferred: null,
          explanation: null,
          relaxed_alternative: relaxed,
          no_feasible_route: {
            code: 'hard_constraints',
            message: 'No route satisfies your hard limits.',
            blocking_reasons: ['mapped steps (highway=steps)'],
            shortest_route_available: true,
            relaxed_alternative_available: true,
          },
        })}
      />,
    );
    expect(screen.getByText('No route meets your hard limits')).toBeInTheDocument();
    expect(screen.getByText(/mapped steps/)).toBeInTheDocument();
    expect(screen.getByText(/clearly labeled alternative/)).toBeInTheDocument();
    expect(screen.getByText(/Relaxed alternative: steps allowed/)).toBeInTheDocument();
  });
});
