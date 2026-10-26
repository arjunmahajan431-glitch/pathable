import L, { type LeafletEvent } from 'leaflet';
import { useEffect, useMemo } from 'react';
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet';

import type { Theme } from '../hooks/useTheme';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import { useRoutePlayback } from '../hooks/useRoutePlayback';
import type { Area, AreaBoundary, Point, Route, RouteResponse } from '../lib/types';
import { Legend } from './Legend';

interface MapPanelProps {
  area: Area | null;
  theme: Theme;
  start: Point | null;
  end: Point | null;
  result: RouteResponse | null;
  pointMode: 'start' | 'end';
  selectedSegmentId: string | null;
  onMapClick: (point: Point) => void;
  onSelectSegment: (segmentId: string) => void;
}

function boundaryRings(boundary: AreaBoundary | null | undefined): [number, number][][] {
  if (!boundary) return [];
  const toLatLng = (ring: [number, number][]): [number, number][] =>
    ring.map(([lon, lat]) => [lat, lon]);
  if (boundary.type === 'Polygon') return boundary.coordinates.map(toLatLng);
  return boundary.coordinates.flatMap((polygon) => polygon.map(toLatLng));
}

function MapAccessibleName() {
  const map = useMap();
  useEffect(() => {
    // Leaflet makes its container focusable; give it a name so a screen reader
    // announces what receives focus. All route content is also available as
    // text in the planning panel and segment list.
    map
      .getContainer()
      .setAttribute(
        'aria-label',
        'Street map with the shortest and preferred routes. Route details are listed below the map.',
      );
  }, [map]);
  return null;
}

function ClickHandler({ onClick }: { onClick: (point: Point) => void }) {
  useMapEvents({
    click(event) {
      onClick({ lat: event.latlng.lat, lon: event.latlng.lng });
    },
  });
  return null;
}

function FitRoute({
  result,
  start,
  end,
  reducedMotion,
}: {
  result: RouteResponse | null;
  start: Point | null;
  end: Point | null;
  reducedMotion: boolean;
}) {
  const map = useMap();
  const bounds = useMemo(() => {
    const route = result?.preferred ?? result?.shortest;
    if (route?.geometry.coordinates.length) {
      return L.latLngBounds(
        route.geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]),
      );
    }
    if (start && end) {
      return L.latLngBounds(
        [start.lat, start.lon],
        [end.lat, end.lon],
      ).pad(0.25);
    }
    return null;
  }, [result, start, end]);

  useEffect(() => {
    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [36, 36], animate: !reducedMotion, maxZoom: 17 });
    }
  }, [map, bounds, reducedMotion]);

  return null;
}

function routePositions(route: Route | null): [number, number][] {
  if (!route) return [];
  return route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
}

function stopAndSelect(event: LeafletEvent, segmentId: string, onSelect: (id: string) => void) {
  L.DomEvent.stopPropagation(event);
  onSelect(segmentId);
}

const PLAYBACK_DOT = L.divIcon({
  className: '',
  html: '<span class="route-dot"></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

export function MapPanel({
  area,
  theme,
  start,
  end,
  result,
  pointMode,
  selectedSegmentId,
  onMapClick,
  onSelectSegment,
}: MapPanelProps) {
  const reducedMotion = usePrefersReducedMotion();
  const shortest = result?.shortest ?? null;
  const preferred = result?.preferred ?? null;
  const playback = useRoutePlayback(preferred, !reducedMotion);
  const selected = preferred?.segments.find((segment) => segment.id === selectedSegmentId) ?? null;
  const center = area?.center ?? { lat: 44.918888, lon: -92.936638 };
  const rings = boundaryRings(area?.boundary);
  const mapTarget = pointMode === 'start' ? start : end;
  const dark = theme === 'dark';
  const colors = {
    preferred: dark ? '#60a5fa' : '#1d4ed8',
    shortest: dark ? '#fbbf24' : '#b45309',
    unknown: dark ? '#c4b5fd' : '#7c3aed',
    selected: dark ? '#f8fafc' : '#0f172a',
    flow: dark ? '#e0f2fe' : '#93c5fd',
    boundary: dark ? '#94a3b8' : '#475569',
  };

  return (
    <section
      aria-labelledby="map-heading"
      className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2.5 dark:border-slate-700">
        <h2 id="map-heading" className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Map workspace
        </h2>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Visual supplement. Every route is also described in the segment list below.
        </p>
      </div>
      <div
        className="relative h-[48vh] min-h-[340px] w-full lg:h-[58vh]"
        role="region"
        aria-label={`Interactive map. Click the map to set the ${pointMode === 'start' ? 'start' : 'destination'}. A keyboard- and screen-reader-friendly coordinate form is in the planning panel.`}
      >
        <MapContainer
          key={area?.id ?? 'default-area'}
          center={[center.lat, center.lon]}
          zoom={12}
          scrollWheelZoom
          zoomAnimation={!reducedMotion}
          fadeAnimation={!reducedMotion}
          markerZoomAnimation={!reducedMotion}
          className="h-full w-full"
        >
          <MapAccessibleName />
          <TileLayer
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          <ClickHandler onClick={onMapClick} />
          {rings.map((ring, index) => (
            <Polygon
              key={`area-ring-${index}`}
              positions={ring}
              interactive={false}
              pathOptions={{
                color: colors.boundary,
                weight: 1.4,
                opacity: 0.7,
                fill: false,
                dashArray: '4 7',
              }}
            />
          ))}
          <FitRoute result={result} start={start} end={end} reducedMotion={reducedMotion} />

          {shortest && (
            <Polyline
              positions={routePositions(shortest)}
              pathOptions={{
                color: colors.shortest,
                weight: 5,
                opacity: 0.95,
                dashArray: '10 8',
              }}
            >
              <Tooltip sticky>Length-only shortest route</Tooltip>
            </Polyline>
          )}
          {preferred && (
            <Polyline
              positions={routePositions(preferred)}
              pathOptions={{
                color: colors.preferred,
                weight: 6,
                opacity: 0.95,
                className: playback.playing ? 'route-active' : undefined,
              }}
            >
              <Tooltip sticky>Preferred route</Tooltip>
            </Polyline>
          )}
          {preferred && playback.playing && (
            <Polyline
              positions={routePositions(preferred)}
              pathOptions={{
                color: colors.flow,
                weight: 3,
                opacity: 1,
                className: 'route-flow',
              }}
            />
          )}
          {preferred && playback.playing && playback.point && (
            <Marker
              position={playback.point}
              icon={PLAYBACK_DOT}
              interactive={false}
              keyboard={false}
              title="Moving position on the preferred route"
            />
          )}
          {preferred &&
            preferred.segments
              .filter((segment) => segment.unknown_attributes.length > 0)
              .map((segment) => (
                <Polyline
                  key={`unknown-${segment.id}`}
                  positions={segment.coords.map(([lon, lat]) => [lat, lon])}
                  pathOptions={{
                    color: colors.unknown,
                    weight: 9,
                    opacity: 0.55,
                    dashArray: '1 7',
                    lineCap: 'round',
                  }}
                  eventHandlers={{
                    click: (event) => stopAndSelect(event, segment.id, onSelectSegment),
                  }}
                />
              ))}
          {preferred?.segments.map((segment) => (
            <Polyline
              key={`segment-${segment.id}`}
              positions={segment.coords.map(([lon, lat]) => [lat, lon])}
              pathOptions={{
                color: segment.id === selectedSegmentId ? colors.selected : colors.preferred,
                weight: segment.id === selectedSegmentId ? 11 : 6,
                opacity: segment.id === selectedSegmentId ? 0.65 : 0.01,
              }}
              eventHandlers={{
                click: (event) => stopAndSelect(event, segment.id, onSelectSegment),
              }}
            />
          ))}
          {selected && (
            <Polyline
              positions={selected.coords.map(([lon, lat]) => [lat, lon])}
              pathOptions={{ color: colors.selected, weight: 10, opacity: 0.55 }}
            >
              <Tooltip sticky>Selected segment. See the details below.</Tooltip>
            </Polyline>
          )}
          {start && (
            <CircleMarker
              center={[start.lat, start.lon]}
              radius={9}
              pathOptions={{ color: '#0f172a', weight: 2, fillColor: '#ffffff', fillOpacity: 1 }}
            >
              <Tooltip permanent direction="top">Start</Tooltip>
            </CircleMarker>
          )}
          {end && (
            <CircleMarker
              center={[end.lat, end.lon]}
              radius={9}
              pathOptions={{ color: '#0f172a', weight: 2, fillColor: '#0f172a', fillOpacity: 1 }}
            >
              <Tooltip permanent direction="top">Destination</Tooltip>
            </CircleMarker>
          )}
        </MapContainer>
        {!(start && end) ? (
          <div className="pointer-events-none absolute left-14 top-3 z-[500] max-w-[calc(100%-4.25rem)] rounded-full bg-slate-900/90 px-3 py-1 text-xs font-medium text-white shadow-sm">
            Click map: {mapTarget ? 'update' : 'set'}{' '}
            {pointMode === 'start' ? 'start' : 'destination'}
          </div>
        ) : null}
        {area ? (
          <div className="pointer-events-none absolute right-3 top-3 z-[500] hidden items-center gap-1.5 rounded-full border border-slate-200/80 bg-white/95 px-3 py-1 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-900/95 dark:text-slate-200 sm:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
            {area.name}
          </div>
        ) : null}
        {preferred && (
          <div className="absolute bottom-3 left-3 z-[500] flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-2 py-1.5 text-xs shadow-lg backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
            <button
              type="button"
              onClick={playback.toggle}
              disabled={reducedMotion}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-blue-800 px-3 py-1 font-semibold text-white transition hover:bg-blue-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-not-allowed disabled:bg-slate-400 dark:bg-blue-600 dark:hover:bg-blue-500 dark:disabled:bg-slate-700"
              title={
                reducedMotion
                  ? 'Route animation is off because reduced motion is enabled.'
                  : 'Animate a dot along the preferred route.'
              }
            >
              <span aria-hidden="true">{playback.playing ? '❚❚' : '▶'}</span>
              {playback.playing ? 'Pause route' : reducedMotion ? 'Animation off' : 'Play route'}
            </button>
            <div
              role="progressbar"
              aria-label="Route animation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(playback.progress * 100)}
              className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
            >
              <div
                className="h-full rounded-full bg-blue-700 dark:bg-blue-400"
                style={{ width: `${Math.round(playback.progress * 100)}%` }}
              />
            </div>
            <span className="tabular-nums text-slate-600 dark:text-slate-400">
              {Math.round(playback.progress * 100)}%
            </span>
          </div>
        )}
        <div className="absolute bottom-3 right-3 z-[500] hidden max-w-xs md:block">
          <Legend compact />
        </div>
      </div>
      <div className="border-t border-slate-200 dark:border-slate-700 p-3 md:hidden">
        <Legend />
      </div>
    </section>
  );
}
