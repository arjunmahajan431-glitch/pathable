import { useEffect, useRef, useState, type FormEvent } from 'react';

import { createReport } from '../lib/api';
import { formatCoord } from '../lib/format';
import { ApiError, type Point } from '../lib/types';

const CATEGORIES = [
  { value: 'blocked_sidewalk', label: 'Sidewalk blocked' },
  { value: 'missing_or_damaged_curb_ramp', label: 'Missing or damaged curb ramp' },
  { value: 'stairs_or_inaccessible_entrance', label: 'Stairs or inaccessible entrance' },
  { value: 'rough_or_damaged_pavement', label: 'Rough or damaged pavement' },
  { value: 'construction', label: 'Construction' },
  { value: 'other', label: 'Other' },
];

interface ReportDialogProps {
  open: boolean;
  initialPoint: Point;
  areaName: string;
  onClose: () => void;
}

export function ReportDialog({ open, initialPoint, areaName, onClose }: ReportDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const categoryRef = useRef<HTMLSelectElement>(null);
  const [category, setCategory] = useState(CATEGORIES[0]?.value ?? 'other');
  const [description, setDescription] = useState('');
  const [latText, setLatText] = useState(formatCoord(initialPoint.lat));
  const [lonText, setLonText] = useState(formatCoord(initialPoint.lon));
  const [website, setWebsite] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLatText(formatCoord(initialPoint.lat));
      setLonText(formatCoord(initialPoint.lon));
      setSuccess(null);
      setError(null);
      const dialog = dialogRef.current;
      if (dialog && !dialog.open) {
        dialog.showModal();
        window.setTimeout(() => categoryRef.current?.focus(), 0);
      }
    } else {
      dialogRef.current?.close();
    }
  }, [open, initialPoint.lat, initialPoint.lon]);

  const close = () => {
    dialogRef.current?.close();
    onClose();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const lat = Number(latText);
    const lon = Number(lonText);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setError('Enter decimal latitude and longitude.');
      return;
    }
    setSubmitting(true);
    try {
      const response = await createReport({
        lat,
        lon,
        category,
        description: description.trim(),
        website,
      });
      setSuccess(response.message);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'The report could not be sent. Please try again later.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="report-title"
      aria-describedby="report-privacy"
      className="m-auto w-[min(94vw,560px)] rounded-2xl border border-slate-300 bg-white p-0 shadow-2xl backdrop:bg-slate-900/50 dark:border-slate-600 dark:bg-slate-900"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <div className="max-h-[85vh] overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="report-title" className="text-xl font-bold text-slate-900 dark:text-slate-100">
              Report a problem
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              For a barrier or condition in {areaName}. Reports are unverified until a
              reviewer checks them.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            className="min-h-11 min-w-11 rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          >
            Close
          </button>
        </div>

        {success ? (
          <div className="mt-4 space-y-3">
            <p role="status" className="rounded-lg border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/40 p-3 text-sm text-emerald-950 dark:text-emerald-100">
              {success}
            </p>
            <button
              type="button"
              onClick={close}
              className="min-h-11 rounded-md bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-4 space-y-3">
            <p id="report-privacy" className="rounded-md bg-slate-50 dark:bg-slate-800/60 p-2 text-xs text-slate-700 dark:text-slate-300">
              Do not include names, contact details, or other personal information. We store
              only the report text, category and location; no account is needed.
            </p>

            <div>
              <label htmlFor="report-category" className="block text-sm font-semibold text-slate-800 dark:text-slate-200">
                Category
              </label>
              <select
                id="report-category"
                ref={categoryRef}
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="mt-1 min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
              >
                {CATEGORIES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="report-description" className="block text-sm font-semibold text-slate-800 dark:text-slate-200">
                Description (optional, 500 characters max)
              </label>
              <textarea
                id="report-description"
                value={description}
                maxLength={500}
                rows={3}
                onChange={(event) => setDescription(event.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-600 p-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                placeholder="What is there? Is it temporary? Which side of the street?"
              />
              <p className="text-right text-xs text-slate-500 dark:text-slate-400">{description.length}/500</p>
            </div>

            <fieldset>
              <legend className="text-sm font-semibold text-slate-800 dark:text-slate-200">Location</legend>
              <div className="mt-1 grid grid-cols-2 gap-2">
                <div>
                  <label htmlFor="report-lat" className="block text-xs text-slate-600 dark:text-slate-400">
                    Latitude
                  </label>
                  <input
                    id="report-lat"
                    type="text"
                    inputMode="decimal"
                    value={latText}
                    onChange={(event) => setLatText(event.target.value)}
                    className="min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                  />
                </div>
                <div>
                  <label htmlFor="report-lon" className="block text-xs text-slate-600 dark:text-slate-400">
                    Longitude
                  </label>
                  <input
                    id="report-lon"
                    type="text"
                    inputMode="decimal"
                    value={lonText}
                    onChange={(event) => setLonText(event.target.value)}
                    className="min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                  />
                </div>
              </div>
            </fieldset>

            <div className="absolute left-[-10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
              <label htmlFor="report-website">Leave this field blank</label>
              <input
                id="report-website"
                name="website"
                type="text"
                tabIndex={-1}
                autoComplete="off"
                value={website}
                onChange={(event) => setWebsite(event.target.value)}
              />
            </div>

            {error && (
              <p role="alert" className="rounded-md border border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-950/40 p-2 text-sm text-rose-950 dark:text-rose-100">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="min-h-11 w-full rounded-md bg-blue-800 px-4 text-sm font-bold text-white transition hover:bg-blue-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-800 disabled:opacity-60 dark:bg-blue-600 dark:hover:bg-blue-500"
            >
              {submitting ? 'Sending…' : 'Send report for review'}
            </button>
          </form>
        )}
      </div>
    </dialog>
  );
}
