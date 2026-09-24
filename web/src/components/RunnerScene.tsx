import { useEffect, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { MathUtils } from "three";
import { MessageCircle } from "lucide-react";
import type { FrozenHeadStatePark, RunnerState } from "@/types/models";
import { Landscape } from "./scene/Landscape";
import { TrailRunner } from "./scene/TrailRunner";
import { runnerSpeed } from "./scene/motion";
import type { SceneMotion } from "./scene/motion";
import { Atmosphere } from "./scene/Atmosphere";
import { WeatherEffects } from "./scene/WeatherEffects";
import { sceneConditions } from "./scene/conditions";
import type { AtmosphereState, Conditions } from "./scene/conditions";

function World({ speed, conditions, terrain, hasRunner, snap }: {
  speed: number; conditions: Conditions; terrain?: string; hasRunner: boolean; snap: boolean;
}) {
  const atmosphere = useRef<AtmosphereState>({ rain: 0, wind: 0, wetness: 0, night: 0 });
  const motion = useRef<SceneMotion>({ distance: 0, phase: 0, speed, time: 0 });
  useFrame((_, delta) => {
    if (snap) { motion.current.speed = speed; return; }
    // Ignore a long first frame after resuming a hidden tab/slide.
    const dt = Math.min(delta, 0.05);
    motion.current.speed = MathUtils.damp(motion.current.speed, speed, 5, dt);
    if (speed === 0 && motion.current.speed < 0.01) motion.current.speed = 0;
    motion.current.distance += motion.current.speed * dt;
    motion.current.phase += motion.current.speed * dt * 5;
    motion.current.time += dt;
  }, -1);
  return (
    <>
      <Atmosphere conditions={conditions} atmosphereRef={atmosphere} snap={snap} />
      <Landscape motion={motion} label={terrain} atmosphere={atmosphere} snap={snap} />
      <WeatherEffects atmosphere={atmosphere} motion={motion} />
      {hasRunner && <TrailRunner motion={motion} />}
    </>
  );
}

export default function RunnerScene({ runner, environment, monologue, active }: {
  runner?: RunnerState;
  environment: FrozenHeadStatePark | null;
  monologue?: string;
  active: boolean;
}) {
  const [visible, setVisible] = useState(!document.hidden);
  const [expandedThought, setExpandedThought] = useState<string | null>(null);
  const expanded = expandedThought === (monologue ?? runner?.last_decision?.monologue);
  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  const speed = runnerSpeed(runner);
  const conditions = sceneConditions(environment);
  const text = monologue ?? runner?.last_decision?.monologue;
  const long = (text?.length ?? 0) > 160;
  const excerpt = long && !expanded ? `${text!.slice(0, 157).replace(/\s+\S*$/, "")}…` : text;

  return (
    <div className="runner-scene">
      <Canvas
        shadows dpr={[1, 1.5]} camera={{ position: [4.2, 4.1, 9], fov: 46, near: 0.1, far: 190 }}
        frameloop={active && visible ? "always" : "demand"}
        gl={{ antialias: true, powerPreference: "low-power" }}
        onCreated={({ camera }) => camera.lookAt(0, 1.6, -5)}
        fallback={<div className="scene-placeholder">This browser cannot display 3D. The map is still available.</div>}
      >
        <World hasRunner={Boolean(runner)} speed={speed} conditions={conditions}
          terrain={runner?.current_terrain} snap={!active || !visible} />
      </Canvas>
      <div className="scene-vignette" />
      <div className="scene-kicker"><span className="scene-indicator" />{conditions.weather} <span>/ {environment?.local_time?.replace(/^Day \d+,\s*/, "") ?? "Runner view"}</span></div>
      {runner ? (
        <>
          <div className="runner-thought" key={runner.persona_name}>
            <div className="runner-thought-heading"><MessageCircle size={13} /><span>{runner.persona_name}’s inner voice</span></div>
            <p aria-live="polite">{excerpt || "Waiting for the first thought…"}</p>
            {long && <button type="button" onClick={() => setExpandedThought(expanded ? null : text ?? null)} aria-expanded={expanded}>{expanded ? "Less" : "Read full thought"}<span aria-hidden="true"> {expanded ? "−" : "+"}</span></button>}
          </div>
          <div className="scene-runner-caption"><span className="scene-bib">{String(runner.bib_number).padStart(2, "0")}</span><div><strong>{runner.persona_name}</strong><span>Loop {runner.loop} · {runner.books_found} books found</span><span className="scene-terrain-label">{runner.current_terrain}</span></div></div>
        </>
      ) : <div className="scene-empty">A quiet trail. Start a run to meet your runner.</div>}
      <div className="scene-footer">
        <div><span className="scene-footer-label">{speed > 0 ? "Current pace" : "On the trail"}</span><span className="scene-pace">{runner ? speed > 0 ? `${runner.pace_min_per_km.toFixed(1)}` : "Resting" : "Waiting"}{speed > 0 && <small> min/km</small>}</span></div>
      </div>
    </div>
  );
}
