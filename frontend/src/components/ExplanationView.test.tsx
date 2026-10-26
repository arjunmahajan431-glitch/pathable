import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ExplanationView } from './ExplanationView';
import { COVERAGE, EXPLANATION, SENSITIVITY } from '../test/fixtures';

describe('ExplanationView', () => {
  it('renders the deterministic explanation sections', () => {
    render(
      <ExplanationView
        explanation={EXPLANATION}
        coverage={COVERAGE}
        warnings={[
          { code: 'dem_grade', message: 'Some slopes are estimated.', severity: 'warning' },
        ]}
        sensitivity={SENSITIVITY}
      />,
    );
    expect(screen.getByText(/The preferred route is 380 m/)).toBeInTheDocument();
    expect(screen.getByText('Why this route')).toBeInTheDocument();
    expect(screen.getByText('Why not the shortest route')).toBeInTheDocument();
    expect(screen.getByText(/BLOCKED/)).toBeInTheDocument();
    expect(screen.getByText(/Coverage measures mapping completeness/)).toBeInTheDocument();
    expect(screen.getByText('Sensitivity check')).toBeInTheDocument();
    expect(screen.getByText('Route changes')).toBeInTheDocument();
    expect(screen.getByText('Same route')).toBeInTheDocument();
    expect(screen.getByText(/Some slopes are estimated/)).toBeInTheDocument();
    expect(screen.getByText(/no external service is called/)).toBeInTheDocument();
  });

  it('shows per-attribute coverage percentages', () => {
    render(
      <ExplanationView
        explanation={EXPLANATION}
        coverage={COVERAGE}
        warnings={[]}
        sensitivity={[]}
      />,
    );
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText(/83% mapped overall/)).toBeInTheDocument();
  });
});
