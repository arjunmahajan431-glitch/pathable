import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { AreaSwitcher } from './components/AreaSwitcher';
import { Banner } from './components/Banner';
import { ComparisonCards } from './components/ComparisonCards';
import { ExplanationView } from './components/ExplanationView';
import { MapPanel } from './components/MapPanel';
import { PlanningPanel } from './components/PlanningPanel';
import { ReportDialog } from './components/ReportDialog';
import { SegmentInspector } from './components/SegmentInspector';
import { ThemeToggle } from './components/ThemeToggle';
import { useTheme } from './hooks/useTheme';
import { activateArea, fetchHealth, fetchProfiles, planRoute } from './lib/api';
import {
  ApiError,
  type HealthResponse,
  type Point,
  type Profile,
  type ProfilesResponse,
  type Risk,
  type RouteResponse,
} from './lib/types';

const FALLBACK_CENTER: Point = { lat: 44.918888, lon: -92.936638 };

function BrandMark() {
  return (
    <span
      className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-lg shadow-blue-900/20"
      aria-hidden="true"
    >
      <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M5 19c0-5 3-4 5-7s0-6 4-7 4 3 4 6" strokeLinecap="round" />
        <circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none" />
        <circle cx="18" cy="11" r="1.6" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [profilesData, setProfilesData] = useState<ProfilesResponse | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [loadingBoot, setLoadingBoot] = useState(true);
  const [selectedName, setSelectedName] = useState('wheelchair');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [risk, setRisk] = useState<Risk>('balanced');
  const [start, setStart] = useState<Point | null>(null);
  const [end, setEnd] = useState<Point | null>(null);
  const [pointMode, setPointMode] = useState<'start' | 'end'>('start');
  const [result, setResult] = useState<RouteResponse | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [reportOpen, setReportOpen] = useState(false);
  const [switchingArea, setSwitchingArea] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoadingBoot(true);
    setBootError(null);
    try {
      const [healthResponse, profilesResponse] = await Promise.all([
        fetchHealth(),
        fetchProfiles(),
      ]);
      setHealth(healthResponse);
      setProfilesData(profilesResponse);
      const preferred =
        profilesResponse.profiles.find((item) => item.name === 'wheelchair') ??
        profilesResponse.profiles[0] ??
        null;
      if (preferred) {
        setSelectedName(preferred.name);
        setProfile(preferred);
      }
    } catch (error) {
      setBootError(
        error instanceof ApiError
          ? error.message
          : 'Could not load the PathAble service. Check that the backend is running.',
      );
    } finally {
      setLoadingBoot(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (result) {
      // Move assistive-technology focus to the result without yanking the map
      // out of view. The visible page stays at the route so the path and the
      // animation remain on screen; the live region announces the outcome.
      resultsRef.current?.focus({ preventScroll: true });
    }
  }, [result]);

  const settingsDirty = useMemo(() => {
    if (!result || !profile) return false;
    return result.risk !== risk || JSON.stringify(result.profile) !== JSON.stringify(profile);
  }, [result, risk, profile]);

  const handlePlan = async () => {
    if (!start || !end || !profile) return;
    setLoadingRoute(true);
    setRouteError(null);
    setSelectedSegmentId(null);
    try {
      const response = await planRoute({ start, end, profile, risk });
      setResult(response);
      setAnnouncement(
        response.preferred
          ? `${response.explanation?.summary ?? 'Routes ready.'} Select a segment to inspect its cost and data provenance.`
          : (response.no_feasible_route?.message ?? 'No preferred route is available.'),
      );
      if (!response.preferred) {
        setSelectedSegmentId(response.shortest?.barriers[0]?.segment_id ?? null);
      }
    } catch (error) {
      setResult(null);
      setRouteError(
        error instanceof ApiError
          ? error.message
          : 'The route request failed unexpectedly. Please try again.',
      );
      setAnnouncement('The route request failed.');
    } finally {
      setLoadingRoute(false);
    }
  };

  const handleAreaSwitch = async (areaId: string) => {
    if (!health || health.area?.id === areaId || switchingArea) return;
    const target = health.areas.find((item) => item.id === areaId);
    setSwitchingArea(areaId);
    setRouteError(null);
    setAnnouncement(`Loading the ${target?.name ?? areaId} map data. One moment.`);
    try {
      const next = await activateArea(areaId);
      setHealth(next);
      setResult(null);
      setStart(null);
      setEnd(null);
      setSelectedSegmentId(null);
      setPointMode('start');
      setAnnouncement(
        `${next.area?.name ?? 'The new area'} is ready. Set a start and destination.`,
      );
    } catch (error) {
      setRouteError(
        error instanceof ApiError
          ? error.message
          : 'The mapping area could not be changed. Please try again.',
      );
      setAnnouncement('The mapping area could not be changed.');
    } finally {
      setSwitchingArea(null);
    }
  };

  const handleProfileSelect = (name: string) => {
    const next = profilesData?.profiles.find((item) => item.name === name);
    if (next) {
      setSelectedName(next.name);
      setProfile(next);
    }
  };

  const handleResetProfile = () => {
    const next = profilesData?.profiles.find((item) => item.name === selectedName);
    if (next) setProfile(next);
  };

  const invalidateRouteForPointEdit = (message: string) => {
    if (result) {
      setResult(null);
      setSelectedSegmentId(null);
      setAnnouncement(message);
    }
    setRouteError(null);
  };

  const handleStartChange = (point: Point | null) => {
    invalidateRouteForPointEdit('Start changed. Select Find routes to update the route.');
    setStart(point);
  };

  const handleEndChange = (point: Point | null) => {
    invalidateRouteForPointEdit('Destination changed. Select Find routes to update the route.');
    setEnd(point);
  };

  const handleMapClick = (point: Point) => {
    if (pointMode === 'start') {
      handleStartChange(point);
      setPointMode('end');
    } else {
      handleEndChange(point);
    }
  };

  const detailRoute = result?.preferred ?? result?.relaxed_alternative ?? result?.shortest ?? null;
  const selectedSegment =
    detailRoute?.segments.find((segment) => segment.id === selectedSegmentId) ?? null;
  const reportPoint = useMemo<Point>(() => {
    if (selectedSegment?.coords.length) {
      const middle = selectedSegment.coords[Math.floor(selectedSegment.coords.length / 2)];
      if (middle) return { lat: middle[1], lon: middle[0] };
    }
    if (start) return start;
    if (end) return end;
    return result?.area.center ?? health?.area?.center ?? FALLBACK_CENTER;
  }, [selectedSegment, start, end, result, health]);

  if (loadingBoot) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <span
            aria-hidden="true"
            className="h-5 w-5 animate-spin rounded-full border-2 border-blue-700 border-t-transparent dark:border-blue-400 dark:border-t-transparent"
          />
          <p role="status" className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Loading PathAble...
          </p>
        </div>
      </div>
    );
  }

  if (bootError || !health || !profilesData || !profile) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-lg rounded-2xl border border-rose-300 bg-white p-6 shadow-xl dark:border-rose-700 dark:bg-slate-900">
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            PathAble is not available
          </h1>
          <p role="alert" className="mt-2 text-sm text-slate-700 dark:text-slate-300">
            {bootError ?? 'The service did not return the expected startup data.'}
          </p>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Start the backend and frontend with <code>make dev</code>, then retry. If the
            graph is missing, run <code>make data</code>.
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-4 min-h-11 rounded-lg bg-blue-800 px-4 text-sm font-semibold text-white transition hover:bg-blue-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-800 dark:bg-blue-600 dark:hover:bg-blue-500"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const area = result?.area ?? health.area ?? null;

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[1000] focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-blue-800 dark:focus:bg-slate-900 dark:focus:text-blue-300"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-[900] border-b border-slate-200/80 bg-white/85 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-3 px-3 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <BrandMark />
            <p className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
              PathAble
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <AreaSwitcher
              areas={health.areas}
              activeId={health.area?.id ?? null}
              loading={Boolean(switchingArea)}
              onSwitch={(areaId) => void handleAreaSwitch(areaId)}
            />
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
        </div>
        {switchingArea ? (
          <div
            role="status"
            className="flex items-center gap-2 border-t border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-900 dark:border-blue-900 dark:bg-blue-950/60 dark:text-blue-100 sm:px-5"
          >
            <span
              aria-hidden="true"
              className="h-3 w-3 animate-spin rounded-full border-2 border-blue-700 border-t-transparent dark:border-blue-300 dark:border-t-transparent"
            />
            Loading {health.areas.find((item) => item.id === switchingArea)?.name ?? 'map data'}...
          </div>
        ) : null}
      </header>

      <div className="mx-auto max-w-[1500px] space-y-3 px-3 pt-4 sm:px-5">
        <Banner health={health} result={result} />
        {!health.graph_loaded && (
          <div
            role="alert"
            className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-950 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-100"
          >
            <strong>The pedestrian graph is not loaded.</strong> {health.graph_error ?? ''}{' '}
            Route requests will fail until the backend has data.
          </div>
        )}
      </div>

      <main
        id="main"
        className="mx-auto grid max-w-[1500px] gap-4 px-3 py-4 sm:px-5 lg:grid-cols-[minmax(320px,400px)_minmax(0,1fr)]"
      >
        <aside aria-label="Trip planning" className="lg:sticky lg:top-[5.6rem] lg:self-start">
          <PlanningPanel
            profiles={profilesData}
            selectedName={selectedName}
            profile={profile}
            risk={risk}
            start={start}
            end={end}
            pointMode={pointMode}
            loading={loadingRoute}
            onProfileSelect={handleProfileSelect}
            onProfileChange={setProfile}
            onRiskChange={setRisk}
            onResetProfile={handleResetProfile}
            onStartChange={handleStartChange}
            onEndChange={handleEndChange}
            onActivateMap={setPointMode}
            onPlan={() => void handlePlan()}
          />
        </aside>

        <div className="min-w-0 space-y-4">
          <MapPanel
            area={area}
            theme={theme}
            start={start}
            end={end}
            result={result}
            pointMode={pointMode}
            selectedSegmentId={selectedSegmentId}
            onMapClick={handleMapClick}
            onSelectSegment={setSelectedSegmentId}
          />

          <p className="sr-only" aria-live="polite">
            {announcement}
          </p>

          {routeError && (
            <div
              role="alert"
              className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-950 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-100"
            >
              <strong>Route request failed.</strong> {routeError}
            </div>
          )}

          {loadingRoute && (
            <div
              role="status"
              className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-blue-700 border-t-transparent dark:border-blue-400 dark:border-t-transparent"
              />
              Finding routes, pricing unknown data, and checking nearby reports...
            </div>
          )}

          {result && (
            <div
              ref={resultsRef}
              tabIndex={-1}
              aria-label="Route results"
              className="space-y-4 focus:outline-none"
            >
              {settingsDirty && (
                <p className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
                  Your settings changed after this result. Select <strong>Find routes</strong>{' '}
                  to recompute.
                </p>
              )}
              <ComparisonCards result={result} />
              {result.explanation && (
                <ExplanationView
                  explanation={result.explanation}
                  coverage={
                    result.preferred?.coverage ??
                    result.relaxed_alternative?.coverage ??
                    result.shortest?.coverage ?? {
                      attributes: {},
                      overall: null,
                      note: '',
                    }
                  }
                  warnings={result.warnings}
                  sensitivity={result.sensitivity}
                />
              )}
              {detailRoute && (
                <>
                  {!result.preferred && (
                    <p className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-950 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-100">
                      Showing the{' '}
                      {detailRoute.kind === 'relaxed'
                        ? 'relaxed alternative'
                        : 'length-only shortest route'}{' '}
                      below. It does not meet your hard settings.
                    </p>
                  )}
                  <SegmentInspector
                    route={detailRoute}
                    selectedSegmentId={selectedSegmentId}
                    onSelect={setSelectedSegmentId}
                  />
                </>
              )}
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  See a barrier or bad surface that the map misses?
                </p>
                <button
                  type="button"
                  onClick={() => setReportOpen(true)}
                  className="min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Report a problem
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      <footer className="mt-4 border-t border-slate-200/80 bg-white/70 px-3 py-6 text-xs text-slate-600 backdrop-blur dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400 sm:px-5">
        <div className="mx-auto flex max-w-[1500px] flex-wrap justify-between gap-3">
          <p>
            PathAble is a student project. Routing information only. This is not medical,
            legal, or engineering advice, and never a claim of accessibility.
          </p>
          <p>
            Map data ©{' '}
            <a
              className="underline underline-offset-2 hover:text-slate-900 dark:hover:text-slate-200"
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noreferrer"
            >
              OpenStreetMap contributors
            </a>
            , ODbL. Data snapshot {health.data_date ?? 'date unknown'}; not a live map.
            Elevation estimates use SRTM 30 m via OpenTopoData. See the README.
          </p>
        </div>
      </footer>

      <ReportDialog
        open={reportOpen}
        initialPoint={reportPoint}
        areaName={area?.name ?? 'this city'}
        onClose={() => setReportOpen(false)}
      />
    </div>
  );
}
