import { GeoJSONSource, Map as MapLibreMap, Popup } from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { CourseGeometry, RunnerState } from "../types/models";

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string;
const STYLE_URL = `https://api.maptiler.com/maps/streets-v2/style.json?key=${MAPTILER_KEY}`;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

// [lat, lon] on the wire (server/sim/course.py) -> [lon, lat] for GeoJSON/MapLibre.
function toLngLat([lat, lon]: [number, number]): [number, number] {
  return [lon, lat];
}

const RUNNERS_SOURCE_ID = "runners";
const COURSE_SOURCE_ID = "course";
const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

function toRunnerFeatureCollection(
  runners: Record<string, RunnerState>,
): FeatureCollection {
  const features: Feature[] = [];
  for (const runner of Object.values(runners)) {
    const truePos = toLngLat(runner.true_pos);
    const believedPos = toLngLat(runner.believed_pos);
    features.push(
      {
        type: "Feature",
        properties: { kind: "true" },
        geometry: { type: "Point", coordinates: truePos },
      },
      {
        type: "Feature",
        properties: { kind: "believed" },
        geometry: { type: "Point", coordinates: believedPos },
      },
      {
        type: "Feature",
        properties: { kind: "link" },
        geometry: { type: "LineString", coordinates: [truePos, believedPos] },
      },
    );
  }
  return { type: "FeatureCollection", features };
}

function toCourseFeatureCollection(course: CourseGeometry): FeatureCollection {
  const trail: Feature = {
    type: "Feature",
    properties: { kind: "trail" },
    geometry: { type: "LineString", coordinates: course.points.map(toLngLat) },
  };
  const books: Feature[] = course.books.map((book) => ({
    type: "Feature",
    properties: { kind: "book", name: book.name, index: book.index },
    geometry: { type: "Point", coordinates: toLngLat([book.lat, book.lon]) },
  }));
  return { type: "FeatureCollection", features: [trail, ...books] };
}

/** Real dot (true_pos), ghost dot (believed_pos), and a line between them — the "comedy
 * engine" from CLAUDE.md — plus the static course polyline and book markers, fetched once
 * from GET /course rather than re-broadcast every tick (that endpoint's own docstring). */
export function RaceMap({ runners }: { runners: Record<string, RunnerState> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: STYLE_URL,
      center: [-84.73, 36.13], // Frozen Head State Park, TN
      zoom: 12,
    });
    mapRef.current = map;

    let cancelled = false;
    const coursePromise: Promise<CourseGeometry> = fetch(
      `${API_BASE_URL}/course`,
    ).then((r) => r.json());

    map.on("load", () => {
      map.addSource(RUNNERS_SOURCE_ID, { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "link",
        type: "line",
        source: RUNNERS_SOURCE_ID,
        filter: ["==", ["get", "kind"], "link"],
        paint: { "line-color": "#888", "line-dasharray": [2, 2] },
      });
      map.addLayer({
        id: "true",
        type: "circle",
        source: RUNNERS_SOURCE_ID,
        filter: ["==", ["get", "kind"], "true"],
        paint: { "circle-color": "#e63946", "circle-radius": 6 },
      });
      map.addLayer({
        id: "believed",
        type: "circle",
        source: RUNNERS_SOURCE_ID,
        filter: ["==", ["get", "kind"], "believed"],
        paint: {
          "circle-color": "#457b9d",
          "circle-radius": 6,
          "circle-opacity": 0.6,
        },
      });

      map.addSource(COURSE_SOURCE_ID, { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "course-line",
        type: "line",
        source: COURSE_SOURCE_ID,
        filter: ["==", ["get", "kind"], "trail"],
        paint: { "line-color": "#2a9d8f", "line-width": 2 },
      });
      map.addLayer({
        id: "books",
        type: "circle",
        source: COURSE_SOURCE_ID,
        filter: ["==", ["get", "kind"], "book"],
        paint: {
          "circle-color": "#e9c46a",
          "circle-radius": 5,
          "circle-stroke-width": 1,
        },
      });
      map.addLayer({
        id: "book-labels",
        type: "symbol",
        source: COURSE_SOURCE_ID,
        filter: ["==", ["get", "kind"], "book"],
        layout: {
          "text-field": ["get", "name"],
          "text-size": 10,
          "text-offset": [0, 1],
        },
      });

      coursePromise.then((course) => {
        if (cancelled) return;
        const source = map.getSource(COURSE_SOURCE_ID) as GeoJSONSource;
        source.setData(toCourseFeatureCollection(course));
      });

      // Real Barkley rule (ADR-0010): a book's page has to match your bib number to count —
      // flavor text here since course.py doesn't model per-runner book state, just proximity.
      map.on("click", "books", (e) => {
        const feature = e.features?.[0];
        if (!feature || feature.geometry.type !== "Point") return;
        const [lng, lat] = feature.geometry.coordinates;
        new Popup()
          .setLngLat([lng, lat])
          .setHTML(
            `<strong>${feature.properties?.name}</strong><br/>Book #${feature.properties?.name}`,
          )
          .addTo(map);
      });
      map.on("mouseenter", "books", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "books", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    return () => {
      cancelled = true;
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource(RUNNERS_SOURCE_ID) as
      | GeoJSONSource
      | undefined;
    source?.setData(toRunnerFeatureCollection(runners));
  }, [runners]);

  return <div ref={containerRef} className="map" />;
}
