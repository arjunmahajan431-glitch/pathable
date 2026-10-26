import { useEffect, useState, type FormEvent } from 'react';

import { searchAddress } from '../lib/api';
import { formatCoord } from '../lib/format';
import { ApiError, type GeocodeResult, type Point } from '../lib/types';

interface PointInputProps {
  which: 'start' | 'end';
  title: string;
  point: Point | null;
  mapActive: boolean;
  onPointChange: (point: Point | null) => void;
  onActivateMap: () => void;
}

export function PointInput({
  which,
  title,
  point,
  mapActive,
  onPointChange,
  onActivateMap,
}: PointInputProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [latText, setLatText] = useState(point ? formatCoord(point.lat) : '');
  const [lonText, setLonText] = useState(point ? formatCoord(point.lon) : '');
  const [coordError, setCoordError] = useState<string | null>(null);

  useEffect(() => {
    setLatText(point ? formatCoord(point.lat) : '');
    setLonText(point ? formatCoord(point.lon) : '');
  }, [point]);

  const runSearch = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSearchError('Type at least two characters, then press Search.');
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const response = await searchAddress(trimmed);
      setResults(response.results);
      if (response.results.length === 0) {
        setSearchError('No addresses found inside this city. Try a street and number.');
      }
    } catch (error) {
      setSearchError(
        error instanceof ApiError
          ? error.message
          : 'Address search is unavailable. You can type coordinates instead.',
      );
    } finally {
      setSearching(false);
    }
  };

  const applyCoordinates = () => {
    const lat = Number(latText);
    const lon = Number(lonText);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setCoordError('Enter decimal latitude and longitude.');
      return;
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setCoordError('Latitude must be between -90 and 90; longitude between -180 and 180.');
      return;
    }
    setCoordError(null);
    onPointChange({ lat, lon });
  };

  return (
    <section
      aria-labelledby={`${which}-heading`}
      className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 id={`${which}-heading`} className="text-sm font-bold text-slate-900 dark:text-slate-100">
          {title}
        </h3>
        <button
          type="button"
          onClick={onActivateMap}
          aria-pressed={mapActive}
          className={`min-h-11 rounded-md border px-3 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 ${
            mapActive
              ? 'border-blue-700 bg-blue-700 text-white'
              : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
          }`}
        >
          {mapActive ? 'Click the map…' : 'Set on map'}
        </button>
      </div>

      {point ? (
        <p className="mb-2 rounded-md bg-slate-50 dark:bg-slate-800/60 px-2 py-1 text-xs text-slate-700 dark:text-slate-300">
          Selected: {formatCoord(point.lat)}, {formatCoord(point.lon)}{' '}
          <button
            type="button"
            className="ml-2 min-h-11 px-1 font-semibold text-blue-800 dark:text-blue-300 underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
            onClick={() => onPointChange(null)}
          >
            Clear
          </button>
        </p>
      ) : (
        <p className="mb-2 text-xs text-slate-600 dark:text-slate-400">
          Choose a point by address, by coordinates, or on the map.
        </p>
      )}

      <form onSubmit={runSearch} className="space-y-2">
        <label htmlFor={`${which}-address`} className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
          Address or place
        </label>
        <div className="flex gap-2">
          <input
            id={`${which}-address`}
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
            placeholder="e.g. 100 Main St"
            className="min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm text-slate-900 dark:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          />
          <button
            type="submit"
            disabled={searching}
            className="min-h-11 shrink-0 rounded-md bg-slate-900 px-3 text-sm font-semibold text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
          >
            {searching ? 'Searching…' : 'Search'}
          </button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Searches once when you press Search (no search-as-you-type), then caches the
          result. © OpenStreetMap contributors.
        </p>
      </form>

      {searchError && (
        <p role="alert" className="mt-2 text-xs font-medium text-rose-800 dark:text-rose-300">
          {searchError}
        </p>
      )}
      {results.length > 0 && (
        <ul className="mt-2 space-y-1" aria-label={`Address search results for ${title}`}>
          {results.map((result) => (
            <li key={`${result.lat}-${result.lon}-${result.display_name}`}>
              <button
                type="button"
                onClick={() => {
                  onPointChange({ lat: result.lat, lon: result.lon });
                  setResults([]);
                  setQuery('');
                }}
                className="min-h-11 w-full rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-left text-xs text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                title={result.display_name}
              >
                {result.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 border-t border-slate-100 dark:border-slate-800 pt-3">
        <p className="mb-1 text-xs font-semibold text-slate-700 dark:text-slate-300">Typed coordinates</p>
        <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
          <div>
            <label htmlFor={`${which}-lat`} className="block text-xs text-slate-600 dark:text-slate-400">
              Latitude
            </label>
            <input
              id={`${which}-lat`}
              type="text"
              inputMode="decimal"
              value={latText}
              onChange={(event) => setLatText(event.target.value)}
              placeholder="44.918900"
              className="min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
            />
          </div>
          <div>
            <label htmlFor={`${which}-lon`} className="block text-xs text-slate-600 dark:text-slate-400">
              Longitude
            </label>
            <input
              id={`${which}-lon`}
              type="text"
              inputMode="decimal"
              value={lonText}
              onChange={(event) => setLonText(event.target.value)}
              placeholder="-92.936600"
              className="min-h-11 w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
            />
          </div>
          <button
            type="button"
            onClick={applyCoordinates}
            className="min-h-11 rounded-md border border-slate-300 dark:border-slate-600 px-2 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          >
            Apply
          </button>
        </div>
        {coordError && (
          <p role="alert" className="mt-1 text-xs font-medium text-rose-800 dark:text-rose-300">
            {coordError}
          </p>
        )}
      </div>
    </section>
  );
}
