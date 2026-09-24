import { GeoJSONSource, Map as MapLibreMap, Popup } from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { CourseGeometry, RunnerState } from "../types/models";

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string;
// Dark basemap variant — a light "streets" style would fight the Command Center's
// black-ground, cyan-accent identity (direction contract OWN-WORLD).
const STYLE_URL = `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${MAPTILER_KEY}`;
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
  const hasFramedRunner = useRef(false);
  // Mock/live data can arrive (and dispatch into `runners`) before the map's "load" event
  // fires — the style fetch is a network round trip, a synchronous mock dispatch isn't — so
  // the update effect below can run once against an unloaded map and never fire again for
  // this data. The "load" handler reads this ref to hydrate whatever arrived in the meantime.
  const runnersRef = useRef(runners);
  useEffect(() => {
    runnersRef.current = runners;
  });

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: STYLE_URL,
      // Placeholder only — corrected the moment the course or a runner arrives below.
      // Not the true course center (this GPX loop actually sits ~20km east of the park's
      // main entrance), so leaving this uncorrected leaves the polyline/books off-screen.
      center: [-84.73, 36.13],
      zoom: 12,
    });
    mapRef.current = map;
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(containerRef.current);

    let cancelled = false;
    const coursePromise: Promise<CourseGeometry> = fetch(
      `${API_BASE_URL}/course`,
    ).then((r) => r.json());

    map.on("load", () => {
      map.addSource(RUNNERS_SOURCE_ID, {
        type: "geojson",
        data: toRunnerFeatureCollection(runnersRef.current),
      });
      const firstRunner = Object.values(runnersRef.current)[0];
      if (firstRunner && !hasFramedRunner.current) {
        hasFramedRunner.current = true;
        map.jumpTo({ center: toLngLat(firstRunner.true_pos), zoom: 14 });
      }
      // Believed position carries the accent — it's the runner's noisy self-estimate, the
      // product's comedy engine (CLAUDE.md), so it draws the eye; true position stays a
      // quiet, solid ground-truth marker for comparison.
      map.addLayer({
        id: "link",
        type: "line",
        source: RUNNERS_SOURCE_ID,
        filter: ["==", ["get", "kind"], "link"],
        paint: { "line-color": "#00aec7", "line-opacity": 0.5, "line-dasharray": [1, 2] },
      });
      map.addLayer({
        id: "true",
        type: "circle",
        source: RUNNERS_SOURCE_ID,
        filter: ["==", ["get", "kind"], "true"],
        paint: {
          "circle-color": "#f4f5f6",
          "circle-radius": 5,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#000000",
        },
      });
      map.addLayer({
        id: "believed",
        type: "circle",
        source: RUNNERS_SOURCE_ID,
        filter: ["==", ["get", "kind"], "believed"],
        paint: {
          "circle-color": "#00aec7",
          "circle-radius": 7,
          "circle-opacity": 0.85,
          "circle-stroke-width": 4,
          "circle-stroke-color": "#00aec7",
          "circle-stroke-opacity": 0.25,
        },
      });

      map.addSource(COURSE_SOURCE_ID, { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "course-line",
        type: "line",
        source: COURSE_SOURCE_ID,
        filter: ["==", ["get", "kind"], "trail"],
        paint: { "line-color": "#6b6f76", "line-width": 2, "line-dasharray": [3, 2] },
      });
      map.addLayer({
        id: "books",
        type: "circle",
        source: COURSE_SOURCE_ID,
        filter: ["==", ["get", "kind"], "book"],
        paint: {
          "circle-color": "#e8b339",
          "circle-radius": 5,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#000000",
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
        paint: {
          "text-color": "#f4f5f6",
          "text-halo-color": "#000000",
          "text-halo-width": 1,
        },
      });

      coursePromise.then((course) => {
        if (cancelled) return;
        const source = map.getSource(COURSE_SOURCE_ID) as GeoJSONSource;
        source.setData(toCourseFeatureCollection(course));
        // Frame the course itself if no runner has claimed the view yet — otherwise the
        // polyline/books only ever appear once a runner's true_pos happens to land near the
        // hardcoded placeholder center above, which isn't guaranteed for every course file.
        if (!hasFramedRunner.current && course.points.length > 0) {
          const lons = course.points.map(([, lon]) => lon);
          const lats = course.points.map(([lat]) => lat);
          map.fitBounds(
            [
              [Math.min(...lons), Math.min(...lats)],
              [Math.max(...lons), Math.max(...lats)],
            ],
            { padding: 40, duration: 0 },
          );
        }
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
      resizeObserver.disconnect();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const source = map?.getSource(RUNNERS_SOURCE_ID) as
      | GeoJSONSource
      | undefined;
    source?.setData(toRunnerFeatureCollection(runners));

    // Frame the first runner's true position once, so the real/ghost dots — the product's
    // comedy engine — actually land in view instead of relying on the map's static default
    // center; re-centering on every tick would fight anyone panning to inspect the course.
    const firstRunner = Object.values(runners)[0];
    if (map && firstRunner && !hasFramedRunner.current) {
      hasFramedRunner.current = true;
      map.jumpTo({ center: toLngLat(firstRunner.true_pos), zoom: 14 });
    }
  }, [runners]);

  return (
    <div className="relative h-full overflow-hidden">
      {/* maplibre-gl sets this container's inline `position` itself (to `relative`), which
       * would clobber an `absolute inset-0` utility here — plain h-full/w-full sidesteps that. */}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
