import type { FrozenHeadStatePark } from "@/types/models";

export const WEATHER_NAMES = ["clear", "overcast", "rain", "storm", "fog"] as const;
export type Weather = (typeof WEATHER_NAMES)[number];

/** Fictional park clock, not a Date: neither the browser timezone nor race day affects lighting. */
export function parseLocalHour(localTime?: string): number | null {
  const match = /^Day\s+\d+,\s*(\d{1,2}):(\d{2})\s+(AM|PM)\s+ET$/i.exec(localTime?.trim() ?? "");
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 1 || hour > 12 || minute > 59) return null;
  return (hour % 12) + (match[3].toUpperCase() === "PM" ? 12 : 0) + minute / 60;
}

export function weatherName(value?: string): Weather {
  return WEATHER_NAMES.find((name) => name === value) ?? "clear";
}

export interface Conditions {
  hour: number;
  weather: Weather;
  fog: number;
}

export function sceneConditions(environment: FrozenHeadStatePark | null): Conditions {
  return {
    hour: parseLocalHour(environment?.local_time) ?? (environment?.is_daylight === false ? 0 : 12),
    weather: weatherName(environment?.weather),
    fog: Math.max(0, Math.min(100, environment?.fog_pct ?? 0)),
  };
}

// Mutated once per animation frame by Atmosphere; other effects read the blended values.
export interface AtmosphereState {
  rain: number;
  wind: number;
  wetness: number;
  night: number;
}

export const WEATHER_LOOKS = {
  clear: { cloud: 0.05, rain: 0, wind: 0.1, wetness: 0, visibility: 155 },
  overcast: { cloud: 0.8, rain: 0, wind: 0.25, wetness: 0, visibility: 125 },
  rain: { cloud: 0.9, rain: 0.55, wind: 0.35, wetness: 0.8, visibility: 90 },
  storm: { cloud: 1, rain: 1, wind: 1, wetness: 1, visibility: 65 },
  fog: { cloud: 0.65, rain: 0, wind: 0.05, wetness: 0.25, visibility: 55 },
} satisfies Record<Weather, { cloud: number; rain: number; wind: number; wetness: number; visibility: number }>;
