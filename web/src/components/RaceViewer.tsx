import { Component, lazy, Suspense, useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, Footprints, Map as MapIcon } from "lucide-react";
import { RaceMap } from "@/components/Map";
import { Panel } from "@/components/Panel";
import { useAppSelector } from "@/store/hooks";
import type { RunnerState } from "@/types/models";

const RunnerScene = lazy(() => import("@/components/RunnerScene"));

class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? (
      <div className="scene-placeholder">The 3D view couldn’t load. You can still follow the runner on the map.</div>
    ) : this.props.children;
  }
}

export function RaceViewer({ runners }: { runners: Record<string, RunnerState> }) {
  const [slide, setSlide] = useState(0);
  const [hasOpenedScene, setHasOpenedScene] = useState(false);
  const runner = Object.values(runners)[0];
  const environment = useAppSelector((state) => state.race.environment);
  const monologue = useAppSelector((state) =>
    runner ? state.race.monologues[runner.persona_name]?.at(-1)?.text : undefined,
  );

  function selectSlide(next: number) {
    setSlide(next);
    if (next === 1) setHasOpenedScene(true);
  }

  return (
    <Panel className="race-viewer" aria-label="Race views" role="region">
      <div className="race-viewer-header">
        <div className="race-viewer-tabs" role="tablist" aria-label="View">
          {[{ label: "Map", icon: MapIcon }, { label: "Runner", icon: Footprints }].map(({ label, icon: Icon }, index) => (
            <button
              key={label} id={`view-tab-${index}`} role="tab" type="button"
              aria-selected={slide === index} aria-controls={`view-panel-${index}`}
              tabIndex={slide === index ? 0 : -1}
              onClick={() => selectSlide(index)}
              onKeyDown={(event) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - slide;
                selectSlide(next);
                document.getElementById(`view-tab-${next}`)?.focus();
              }}
            ><Icon size={14} />{label}</button>
          ))}
        </div>
        <span className="race-viewer-location">Frozen Head, TN</span>
        <div className="race-viewer-arrows">
          <button type="button" aria-label="Previous view" disabled={slide === 0} onClick={() => selectSlide(0)}><ChevronLeft size={16} /></button>
          <span>0{slide + 1}<span className="text-muted-foreground"> / 02</span></span>
          <button type="button" aria-label="Next view" disabled={slide === 1} onClick={() => selectSlide(1)}><ChevronRight size={16} /></button>
        </div>
      </div>
      <div className="race-viewer-window">
        <div className="race-viewer-track" style={{ transform: `translateX(-${slide * 50}%)` }}>
          <div id="view-panel-0" role="tabpanel" aria-labelledby="view-tab-0" aria-hidden={slide !== 0} inert={slide !== 0} className="race-viewer-slide">
            <RaceMap runners={runners} />
          </div>
          <div id="view-panel-1" role="tabpanel" aria-labelledby="view-tab-1" aria-hidden={slide !== 1} inert={slide !== 1} className="race-viewer-slide">
            {hasOpenedScene && (
              <SceneBoundary>
                <Suspense fallback={<div className="scene-placeholder">Finding a patch of trail…</div>}>
                  <RunnerScene runner={runner} environment={environment} monologue={monologue} active={slide === 1} />
                </Suspense>
              </SceneBoundary>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
