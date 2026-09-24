import { useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { BackSide, Color, DirectionalLight, Fog, HemisphereLight, MathUtils, Mesh, MeshBasicMaterial, ShaderMaterial } from "three";
import type { AtmosphereState, Conditions } from "./conditions";
import { WEATHER_LOOKS } from "./conditions";

const DAY_STOPS = [
  { hour: 0, top: "#102336", horizon: "#405461", light: "#b5d4ef", power: 0.35, ambient: 0.8, night: 1 },
  { hour: 5.5, top: "#172e48", horizon: "#64717c", light: "#b5d4ef", power: 0.4, ambient: 0.85, night: 1 },
  { hour: 7, top: "#8eacae", horizon: "#e8ba90", light: "#ffbc7d", power: 1.5, ambient: 1.3, night: 0.1 },
  { hour: 9, top: "#7caebd", horizon: "#d7e2cf", light: "#fff0cd", power: 2.5, ambient: 1.8, night: 0 },
  { hour: 16, top: "#82adbd", horizon: "#dce2ce", light: "#ffe8ba", power: 2.5, ambient: 1.8, night: 0 },
  { hour: 18.5, top: "#877f9a", horizon: "#edb582", light: "#ffb56f", power: 1.6, ambient: 1.2, night: 0.05 },
  { hour: 20, top: "#172a42", horizon: "#586577", light: "#aac9ed", power: 0.35, ambient: 0.8, night: 1 },
  { hour: 24, top: "#102336", horizon: "#405461", light: "#b5d4ef", power: 0.35, ambient: 0.8, night: 1 },
];

function lightingTarget({ hour, weather, fog }: Conditions) {
  const end = DAY_STOPS.findIndex((stop) => stop.hour > hour);
  const a = DAY_STOPS[Math.max(0, end - 1)];
  const b = DAY_STOPS[end < 0 ? DAY_STOPS.length - 1 : end];
  const mix = MathUtils.smoothstep(hour, a.hour, b.hour);
  const look = WEATHER_LOOKS[weather];
  const night = MathUtils.lerp(a.night, b.night, mix);
  const cloudTint = new Color(night > 0.5 ? "#344652" : weather === "storm" ? "#71818a" : "#bbc4c0");
  const top = new Color(a.top).lerp(new Color(b.top), mix).lerp(cloudTint, look.cloud * 0.9);
  const horizon = new Color(a.horizon).lerp(new Color(b.horizon), mix).lerp(cloudTint, look.cloud * 0.8);
  return {
    top, horizon, light: new Color(a.light).lerp(new Color(b.light), mix).lerp(new Color("#c1d0d7"), look.cloud * 0.8),
    power: MathUtils.lerp(a.power, b.power, mix) * (1 - look.cloud * 0.8),
    ambient: MathUtils.lerp(a.ambient, b.ambient, mix) * (weather === "storm" ? 0.75 : 1),
    far: Math.max(30, look.visibility - fog * 0.45),
    near: weather === "fog" ? 3 : 12,
    night, ...look,
  };
}

const skyVertex = `
  varying vec3 vDirection;
  void main() {
    vDirection = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const skyFragment = `
  uniform vec3 topColor;
  uniform vec3 horizonColor;
  uniform float night;
  uniform float cloud;
  varying vec3 vDirection;
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  void main() {
    vec3 direction = normalize(vDirection);
    float height = smoothstep(-0.05, 0.7, direction.y);
    vec3 color = mix(horizonColor, topColor, height);
    vec2 stars = vec2(atan(direction.x, direction.z), asin(direction.y)) * 170.0;
    float star = step(0.992, hash(floor(stars))) * (1.0 - smoothstep(0.02, 0.12, length(fract(stars) - 0.5)));
    color += vec3(star * night * (1.0 - cloud) * height * 0.75);
    gl_FragColor = vec4(color, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

export function Atmosphere({ conditions, atmosphereRef, snap }: {
  conditions: Conditions; atmosphereRef: RefObject<AtmosphereState>; snap: boolean;
}) {
  const [initial] = useState(() => lightingTarget(conditions));
  const target = useMemo(() => lightingTarget(conditions), [conditions]);
  const sun = useRef<DirectionalLight>(null);
  const fill = useRef<DirectionalLight>(null);
  const ambient = useRef<HemisphereLight>(null);
  const fog = useRef<Fog>(null);
  const disk = useRef<Mesh>(null);
  const diskMaterial = useRef<MeshBasicMaterial>(null);
  const sky = useRef<ShaderMaterial>(null);
  // Uniform objects must survive React updates; the frame loop blends their values.
  const [uniforms] = useState(() => ({
    topColor: { value: initial.top.clone() }, horizonColor: { value: initial.horizon.clone() },
    night: { value: initial.night }, cloud: { value: initial.cloud },
  }));
  const initialized = useRef(false);
  useFrame((_, delta) => {
    if (!sky.current) return;
    const uniforms = sky.current.uniforms;
    const alpha = snap || !initialized.current ? 1 : 1 - Math.exp(-Math.min(delta, 0.05) * 1.5);
    initialized.current = true;
    uniforms.topColor.value.lerp(target.top, alpha);
    uniforms.horizonColor.value.lerp(target.horizon, alpha);
    uniforms.night.value = MathUtils.lerp(uniforms.night.value, target.night, alpha);
    uniforms.cloud.value = MathUtils.lerp(uniforms.cloud.value, target.cloud, alpha);
    atmosphereRef.current.rain = MathUtils.lerp(atmosphereRef.current.rain, target.rain, alpha);
    atmosphereRef.current.wind = MathUtils.lerp(atmosphereRef.current.wind, target.wind, alpha);
    atmosphereRef.current.wetness = MathUtils.lerp(atmosphereRef.current.wetness, target.wetness, alpha);
    atmosphereRef.current.night = uniforms.night.value;
    if (fog.current) {
      fog.current.color.copy(uniforms.horizonColor.value);
      fog.current.near = MathUtils.lerp(fog.current.near, target.near, alpha);
      fog.current.far = MathUtils.lerp(fog.current.far, target.far, alpha);
    }
    if (fill.current) fill.current.intensity = 0.18 + uniforms.night.value * 0.5;
    if (ambient.current) {
      ambient.current.color.copy(uniforms.horizonColor.value).lerp(target.light, 0.65);
      ambient.current.intensity = MathUtils.lerp(ambient.current.intensity, target.ambient, alpha);
    }
    const angle = ((conditions.hour - (target.night > 0.5 ? 19 : 7)) / 12) * Math.PI;
    const x = -Math.cos(angle) * 35;
    const y = Math.max(4, Math.sin(angle) * 45);
    if (sun.current) {
      sun.current.color.lerp(target.light, alpha);
      sun.current.intensity = MathUtils.lerp(sun.current.intensity, target.power, alpha);
      sun.current.position.x = MathUtils.lerp(sun.current.position.x, x, alpha);
      sun.current.position.y = MathUtils.lerp(sun.current.position.y, y, alpha);
    }
    if (diskMaterial.current) {
      diskMaterial.current.color.lerp(target.light, alpha);
      diskMaterial.current.opacity = 1 - uniforms.cloud.value * 0.9;
    }
    if (disk.current && sun.current) {
      disk.current.position.set(sun.current.position.x * 1.7, sun.current.position.y * 1.3, -105);
      disk.current.scale.setScalar(1 - uniforms.cloud.value * 0.8);
    }
  }, -0.8);
  return (
    <>
      <mesh>
        <sphereGeometry args={[165, 24, 16]} />
        <shaderMaterial ref={sky} side={BackSide} depthWrite={false} uniforms={uniforms} vertexShader={skyVertex} fragmentShader={skyFragment} />
      </mesh>
      <mesh ref={disk} position={[-30, 30, -105]}>
        <sphereGeometry args={[2.1, 16, 12]} />
        <meshBasicMaterial ref={diskMaterial} color={initial.light} transparent opacity={1 - initial.cloud * 0.9} fog={false} />
      </mesh>
      <fog ref={fog} attach="fog" args={[initial.horizon, initial.near, initial.far]} />
      {/* Soft viewer-side fill keeps the runner legible against the dark sky. */}
      <directionalLight ref={fill} position={[4, 6, 8]} color="#b4cee2" intensity={0.25} />
      <hemisphereLight ref={ambient} args={[initial.horizon, "#485346", initial.ambient]} />
      <directionalLight ref={sun} position={[-12, 25, -20]} intensity={initial.power} color={initial.light}
        castShadow shadow-mapSize={[1024, 1024]} shadow-camera-left={-22} shadow-camera-right={22}
        shadow-camera-top={30} shadow-camera-bottom={-22} shadow-camera-far={100}
        shadow-bias={-0.001} shadow-normalBias={0.04} />
    </>
  );
}
