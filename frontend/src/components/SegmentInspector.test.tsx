import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SegmentInspector } from './SegmentInspector';
import { makeRoute, SEGMENT } from '../test/fixtures';

describe('SegmentInspector', () => {
  it('lists segments and opens a full cost breakdown', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { rerender } = render(
      <SegmentInspector
        route={makeRoute()}
        selectedSegmentId={null}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText(/Text version of the map/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Synthetic Street/ }));
    expect(onSelect).toHaveBeenCalledWith('S:B:0');
    rerender(
      <SegmentInspector
        route={makeRoute()}
        selectedSegmentId="S:B:0"
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText('How the effort score is built')).toBeInTheDocument();
    expect(screen.getByText(/6.0% uphill grade/)).toBeInTheDocument();
    expect(screen.getByText(/Unknown for this profile: Smoothness/)).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Term' })).toBeInTheDocument();
  });

  it('flags a hard-blocked segment', () => {
    const blocked = {
      ...SEGMENT,
      id: 'S:A:0',
      cost: {
        ...SEGMENT.cost,
        hard_block: {
          reason: 'mapped steps (highway=steps)',
          attribute: 'steps',
          provenance: 'OSM_MAPPED' as const,
        },
      },
    };
    render(
      <SegmentInspector
        route={makeRoute({ segments: [blocked] })}
        selectedSegmentId={blocked.id}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/Blocked/).length).toBeGreaterThan(0);
    expect(screen.getByText(/mapped steps/)).toBeInTheDocument();
  });

  it('renders an empty route message', () => {
    render(
      <SegmentInspector
        route={makeRoute({ segments: [] })}
        selectedSegmentId={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/No travel needed/)).toBeInTheDocument();
  });
});
