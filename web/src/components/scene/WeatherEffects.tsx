import { useMemo, useRef } from "react";
import type { RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { BufferAttribute, LineBasicMaterial, LineSegments } from "three";
import type { AtmosphereState } from "./conditions";
import type { SceneMotion } from "./motion";
import { seeded } from "./terrain";

const DROP_COUNT = 650;

/** One bounded draw call; weather fades its opacity rather than mounting a new particle system. */
export function WeatherEffects({ atmosphere, motion }: {
  atmosphere: RefObject<AtmosphereState>; motion: RefObject<SceneMotion>;
}) {
  const material = useRef<LineBasicMaterial>(null);
  const lines = useRef<LineSegments>(null);
  const positions = useMemo(() => new Float32Array(DROP_COUNT * 6), []);
  const attribute = useRef<BufferAttribute>(null);
  const drops = useMemo(() => Array.from({ length: DROP_COUNT }, (_, i) => ({
    x: (seeded(i, 80) - 0.5) * 42, y: seeded(i, 81) * 24, z: 12 - seeded(i, 82) * 65,
  })), []);
  useFrame(() => {
    const { rain, wind, night } = atmosphere.current;
    if (lines.current) lines.current.visible = rain > 0.005;
    if (material.current) material.current.opacity = rain * (night > 0.5 ? 0.5 : 0.35);
    if (rain < 0.005) return;
    drops.forEach((drop, index) => {
      const y = ((drop.y - motion.current.time * (14 + wind * 12)) % 24 + 24) % 24;
      const x = drop.x + y * wind * 0.3;
      const offset = index * 6;
      positions[offset] = x; positions[offset + 1] = y; positions[offset + 2] = drop.z;
      positions[offset + 3] = x - wind * 0.38;
      positions[offset + 4] = y - 0.7 - rain * 0.5;
      positions[offset + 5] = drop.z;
    });
    if (attribute.current) attribute.current.needsUpdate = true;
  });
  return (
    <lineSegments ref={lines} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute ref={attribute} attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial ref={material} color="#c9dfdf" transparent opacity={0} depthWrite={false} />
    </lineSegments>
  );
}
