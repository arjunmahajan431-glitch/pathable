import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createReport } from '../lib/api';
import { ReportDialog } from './ReportDialog';

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return { ...actual, createReport: vi.fn() };
});

describe('ReportDialog', () => {
  beforeEach(() => {
    vi.mocked(createReport).mockReset();
  });

  it('submits category, description and coordinates', async () => {
    vi.mocked(createReport).mockResolvedValue({
      id: 12,
      status: 'unverified',
      message: 'Thank you. This report is unverified until a reviewer checks it.',
    });
    const user = userEvent.setup();
    render(
      <ReportDialog
        open
        initialPoint={{ lat: 40.0005, lon: -75.0005 }}
        areaName="Synthetic area"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Report a problem' })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Category'), 'construction');
    await user.type(
      screen.getByLabelText(/Description/),
      'Sidewalk closed by construction.',
    );
    await user.click(screen.getByRole('button', { name: 'Send report for review' }));

    await waitFor(() => expect(createReport).toHaveBeenCalledTimes(1));
    expect(createReport).toHaveBeenCalledWith({
      lat: 40.0005,
      lon: -75.0005,
      category: 'construction',
      description: 'Sidewalk closed by construction.',
      website: '',
    });
    expect(await screen.findByRole('status')).toHaveTextContent(/unverified/);
  });

  it('shows a plain-language error', async () => {
    const { ApiError } = await import('../lib/types');
    vi.mocked(createReport).mockRejectedValue(
      new ApiError('Too many reports from this client in the last hour.', {
        code: 'rate_limited',
        status: 429,
      }),
    );
    const user = userEvent.setup();
    render(
      <ReportDialog
        open
        initialPoint={{ lat: 40.0005, lon: -75.0005 }}
        areaName="Synthetic area"
        onClose={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Send report for review' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Too many reports/);
  });
});
