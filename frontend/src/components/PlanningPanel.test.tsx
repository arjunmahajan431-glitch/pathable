import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PlanningPanel } from './PlanningPanel';
import { PROFILES_RESPONSE, TEST_PROFILE } from '../test/fixtures';

function renderPanel(overrides: Partial<Parameters<typeof PlanningPanel>[0]> = {}) {
  const props: Parameters<typeof PlanningPanel>[0] = {
    profiles: PROFILES_RESPONSE,
    selectedName: 'wheelchair',
    profile: TEST_PROFILE,
    risk: 'balanced',
    start: null,
    end: null,
    pointMode: 'start',
    loading: false,
    onProfileSelect: vi.fn(),
    onProfileChange: vi.fn(),
    onRiskChange: vi.fn(),
    onResetProfile: vi.fn(),
    onStartChange: vi.fn(),
    onEndChange: vi.fn(),
    onActivateMap: vi.fn(),
    onPlan: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<PlanningPanel {...props} />) };
}

describe('PlanningPanel', () => {
  it('requires both endpoints before planning', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: 'Find routes' })).toBeDisabled();
    expect(
      screen.getByText('Set both a start and a destination to continue.'),
    ).toBeInTheDocument();
  });

  it('applies typed coordinates and enables planning', async () => {
    const user = userEvent.setup();
    const { props, rerender } = renderPanel();
    const startRegion = screen.getByRole('region', { name: 'Start' });
    await user.type(within(startRegion).getByLabelText('Latitude'), '40.000000');
    await user.type(within(startRegion).getByLabelText('Longitude'), '-75.000000');
    await user.click(within(startRegion).getByRole('button', { name: 'Apply' }));
    expect(props.onStartChange).toHaveBeenCalledWith({ lat: 40, lon: -75 });

    rerender(
      <PlanningPanel
        {...props}
        start={{ lat: 40, lon: -75 }}
        end={{ lat: 40.002, lon: -75 }}
      />,
    );
    const plan = screen.getByRole('button', { name: 'Find routes' });
    expect(plan).toBeEnabled();
    await user.click(plan);
    expect(props.onPlan).toHaveBeenCalledTimes(1);
  });

  it('updates risk, profile and slider settings', async () => {
    const user = userEvent.setup();
    const { props } = renderPanel();
    await user.click(screen.getByLabelText(/Cautious/));
    expect(props.onRiskChange).toHaveBeenCalledWith('cautious');

    await user.selectOptions(screen.getByLabelText('Mobility profile'), 'limited_mobility');
    expect(props.onProfileSelect).toHaveBeenCalledWith('limited_mobility');

    const slider = screen.getByLabelText('Start penalizing uphill slope above');
    fireEvent.change(slider, { target: { value: '7' } });
    expect(props.onProfileChange).toHaveBeenCalledWith(
      expect.objectContaining({ soft_grade_up_pct: 7 }),
    );
  });

  it('keeps the uphill slope thresholds in a valid order', () => {
    const { props } = renderPanel();
    const soft = screen.getByLabelText('Start penalizing uphill slope above');
    const hard = screen.getByLabelText('Never exceed uphill slope');

    expect(soft).toHaveAttribute('max', '8.33');
    expect(hard).toHaveAttribute('min', '5');

    fireEvent.change(hard, { target: { value: '2' } });
    expect(props.onProfileChange).toHaveBeenCalledWith(
      expect.objectContaining({ hard_grade_up_pct: 5 }),
    );

    fireEvent.change(soft, { target: { value: '20' } });
    expect(props.onProfileChange).toHaveBeenCalledWith(
      expect.objectContaining({ soft_grade_up_pct: 8.33 }),
    );
  });

  it('switches map-selection mode', async () => {
    const user = userEvent.setup();
    const { props } = renderPanel({ pointMode: 'end' });
    const startRegion = screen.getByRole('region', { name: 'Start' });
    await user.click(within(startRegion).getByRole('button', { name: 'Set on map' }));
    expect(props.onActivateMap).toHaveBeenCalledWith('start');
  });
});
