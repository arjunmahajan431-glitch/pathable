import {
  ApiError,
  type Area,
  type GeocodeResponse,
  type HealthResponse,
  type Point,
  type ProfilesResponse,
  type ReportCreateResponse,
  type Report,
  type Risk,
  type RouteResponse,
} from './types';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface ErrorPayload {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 30_000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
    });
    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text) as unknown;
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      const error = (payload as ErrorPayload | null)?.error;
      throw new ApiError(
        error?.message ??
          (response.status === 503
            ? 'The routing service is unavailable right now.'
            : 'The request could not be completed.'),
        {
          code: error?.code ?? `http_${response.status}`,
          status: response.status,
          details: error?.details ?? {},
        },
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The request took too long. Please try again.', {
        code: 'timeout',
      });
    }
    throw new ApiError(
      'Could not reach the PathAble service. Check that the backend is running.',
      { code: 'network' },
    );
  } finally {
    window.clearTimeout(timer);
  }
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health');
}

export function fetchProfiles(): Promise<ProfilesResponse> {
  return request<ProfilesResponse>('/api/profiles');
}

export function fetchAreas(): Promise<{ areas: Area[]; active: Area }> {
  return request<{ areas: Area[]; active: Area }>('/api/areas');
}

export function activateArea(areaId: string): Promise<HealthResponse> {
  return request<HealthResponse>(`/api/areas/${encodeURIComponent(areaId)}/activate`, {
    method: 'POST',
  }, 120_000);
}

export function planRoute(payload: {
  start: Point;
  end: Point;
  profile: string | Record<string, unknown>;
  risk: Risk;
}): Promise<RouteResponse> {
  return request<RouteResponse>('/api/route', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function searchAddress(query: string): Promise<GeocodeResponse> {
  return request<GeocodeResponse>(`/api/geocode?q=${encodeURIComponent(query)}`, {}, 20_000);
}

export function createReport(payload: {
  lat: number;
  lon: number;
  category: string;
  description: string;
  website?: string;
}): Promise<ReportCreateResponse> {
  return request<ReportCreateResponse>('/api/reports', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchReports(bbox: string): Promise<{ count: number; reports: Report[] }> {
  return request<{ bbox: string; count: number; reports: Report[] }>(
    `/api/reports?bbox=${encodeURIComponent(bbox)}`,
  );
}
