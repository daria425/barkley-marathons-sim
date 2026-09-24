import { useEffect, useMemo, useRef } from "react";
import type { RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { CircleGeometry, Color, CylinderGeometry, Group, InstancedMesh, MathUtils, Mesh, MeshStandardMaterial, Object3D, PlaneGeometry } from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { AtmosphereState } from "./conditions";
import type { SceneMotion } from "./motion";
import { seeded, terrainProfile } from "./terrain";
import type { TerrainProfile } from "./terrain";

const TILE_LENGTH = 32;
const TILE_COUNT = 5;
const CURVE_FREQUENCY = Math.PI * 2 / TILE_LENGTH;
const NUMERIC_KEYS = ["width", "curve", "slope", "trees", "pine", "grass", "rocks", "rockScale", "brush", "water", "puddles", "ridge"] as const;

interface TerrainState {
  profile: TerrainProfile;
  ground: Color;
  trail: Color;
  foliage: Color;
  rock: Color;
  version: number;
}

function pathX(z: number, profile: TerrainProfile) {
  return Math.sin(z * CURVE_FREQUENCY) * profile.curve;
}

function groundY(x: number, z: number, profile: TerrainProfile) {
  return -Math.max(0, Math.abs(x - pathX(z, profile)) - 3) * profile.ridge * 0.55;
}

function groundGeometry() {
  const geometry = new PlaneGeometry(70, TILE_LENGTH, 24, 24);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, 0, -TILE_LENGTH / 2);
  return geometry;
}

function pathGeometry() {
  const geometry = new PlaneGeometry(1, TILE_LENGTH, 1, 40);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, 0.015, -TILE_LENGTH / 2);
  return geometry;
}

function briarGeometry() {
  const stem = new CylinderGeometry(0.025, 0.045, 1, 4);
  const left = new CylinderGeometry(0.012, 0.025, 0.65, 4);
  left.rotateZ(0.8);
  left.translate(-0.22, 0.12, 0);
  const right = new CylinderGeometry(0.012, 0.025, 0.65, 4);
  right.rotateZ(-0.8);
  right.translate(0.22, 0.3, 0);
  const geometry = mergeGeometries([stem, left, right]);
  for (const part of [stem, left, right]) part.dispose();
  return geometry;
}

/** Every tile has the same bounded pools. Terrain changes morph their shape and density. */
function TrailTile({ index, motion, terrain, atmosphere }: {
  index: number; motion: RefObject<SceneMotion>; terrain: RefObject<TerrainState>;
  atmosphere: RefObject<AtmosphereState>;
}) {
  const tile = useRef<Group>(null);
  const groundRef = useRef<Mesh>(null);
  const pathRef = useRef<Mesh>(null);
  const trunks = useRef<InstancedMesh>(null);
  const crowns = useRef<InstancedMesh>(null);
  const pines = useRef<InstancedMesh>(null);
  const grass = useRef<InstancedMesh>(null);
  const rocks = useRef<InstancedMesh>(null);
  const brush = useRef<InstancedMesh>(null);
  const thorns = useRef<InstancedMesh>(null);
  const puddles = useRef<InstancedMesh>(null);
  const creek = useRef<Mesh>(null);
  const ripples = useRef<InstancedMesh>(null);
  const groundMaterial = useRef<MeshStandardMaterial>(null);
  const pathMaterial = useRef<MeshStandardMaterial>(null);
  const crownMaterial = useRef<MeshStandardMaterial>(null);
  const pineMaterial = useRef<MeshStandardMaterial>(null);
  const rockMaterial = useRef<MeshStandardMaterial>(null);
  const brushMaterial = useRef<MeshStandardMaterial>(null);
  const seenVersion = useRef(-1);
  const object = useMemo(() => new Object3D(), []);
  const data = useMemo(() => Array.from({ length: 240 }, (_, i) => {
    const seed = index * 500 + i;
    return Array.from({ length: 9 }, (_, salt) => seeded(seed, salt));
  }), [index]);
  // Geometry is owned by the JSX meshes, so R3F disposes it when the scene unmounts.
  const groundMeshGeometry = useMemo(() => groundGeometry(), []);
  const pathMeshGeometry = useMemo(() => pathGeometry(), []);
  const briars = useMemo(() => briarGeometry(), []);
  const puddleGeometry = useMemo(() => {
    const geometry = new CircleGeometry(1, 12);
    geometry.rotateX(-Math.PI / 2);
    return geometry;
  }, []);
  useEffect(() => () => {
    groundMeshGeometry.dispose(); pathMeshGeometry.dispose(); briars.dispose(); puddleGeometry.dispose();
  }, [groundMeshGeometry, pathMeshGeometry, briars, puddleGeometry]);

  function setInstance(ref: RefObject<InstancedMesh | null>, i: number, x: number, y: number, z: number,
    sx: number, sy: number, sz: number, rotation = 0) {
    object.position.set(x, y, z);
    object.scale.set(Math.max(0.0001, sx), Math.max(0.0001, sy), Math.max(0.0001, sz));
    object.rotation.set(0, rotation, 0);
    object.updateMatrix();
    ref.current?.setMatrixAt(i, object.matrix);
  }

  useFrame(() => {
    const state = terrain.current;
    const p = state.profile;
    if (tile.current) tile.current.position.z =
      ((motion.current.distance + index * TILE_LENGTH) % (TILE_COUNT * TILE_LENGTH)) - 96;
    const wet = atmosphere.current.wetness;
    if (groundMaterial.current) groundMaterial.current.color.copy(state.ground).multiplyScalar(1 - wet * 0.18);
    if (pathMaterial.current) {
      pathMaterial.current.color.copy(state.trail).multiplyScalar(1 - wet * 0.25);
      pathMaterial.current.roughness = 1 - Math.max(wet, p.puddles) * 0.65;
    }
    crownMaterial.current?.color.copy(state.foliage);
    pineMaterial.current?.color.copy(state.foliage);
    brushMaterial.current?.color.copy(state.foliage);
    rockMaterial.current?.color.copy(state.rock);
    if (creek.current) {
      creek.current.scale.y = Math.max(0.0001, p.water);
      creek.current.visible = p.water > 0.01;
    }
    if (ripples.current) ripples.current.visible = p.water > 0.01;

    // Rain puddles can grow even when the terrain has stopped morphing.
    for (let i = 0; i < 8; i++) {
      const [a, b, c] = data[i + 190];
      const z = -b * TILE_LENGTH;
      const amount = Math.max(p.puddles, wet * 0.65) * Math.min(1, p.width);
      setInstance(puddles, i, pathX(z, p) + (a - 0.5) * p.width * 0.6, 0.025, z,
        (0.2 + c * 0.55) * amount, 1, (0.4 + a * 0.9) * amount, c * Math.PI);
    }
    if (puddles.current) puddles.current.instanceMatrix.needsUpdate = true;
    if (seenVersion.current === state.version) return;
    seenVersion.current = state.version;

    const ground = groundRef.current?.geometry;
    const path = pathRef.current?.geometry;
    if (!ground || !path) return;
    const groundPositions = ground.attributes.position;
    for (let i = 0; i < groundPositions.count; i++) {
      groundPositions.setY(i, groundY(groundPositions.getX(i), groundPositions.getZ(i), p) - 0.015);
    }
    groundPositions.needsUpdate = true;
    ground.computeVertexNormals();
    ground.computeBoundingSphere();
    const pathPositions = path.attributes.position;
    for (let i = 0; i < pathPositions.count; i++) {
      const z = pathPositions.getZ(i);
      pathPositions.setX(i, pathX(z, p) + (i % 2 ? 0.5 : -0.5) * p.width);
    }
    pathPositions.needsUpdate = true;
    path.computeVertexNormals();
    path.computeBoundingSphere();

    for (let i = 0; i < 32; i++) {
      const [a, b, c, d] = data[i];
      const z = -b * TILE_LENGTH;
      const x = pathX(z, p) + (i % 2 ? 1 : -1) * (p.width / 2 + 2.5 + a * 19);
      const y = groundY(x, z, p);
      const density = MathUtils.clamp((p.trees - c) * 8, 0, 1);
      const height = (3.5 + d * 5.5) * density;
      setInstance(trunks, i, x, y + height / 2, z, height * 0.045, height, height * 0.045);
      const broadleaf = 1 - p.pine;
      setInstance(crowns, i, x, y + height * 0.85, z,
        height * 0.32 * broadleaf, height * 0.48 * broadleaf, height * 0.32 * broadleaf, a * Math.PI);
      setInstance(pines, i, x, y + height * 0.76, z,
        height * 0.32 * p.pine, height * 1.1 * p.pine, height * 0.32 * p.pine);
    }
    for (let i = 0; i < 220; i++) {
      const [a, b, c, d] = data[i];
      const z = -b * TILE_LENGTH;
      const x = pathX(z, p) + (i % 2 ? 1 : -1) * (p.width / 2 + 0.12 + a * 15);
      const height = (0.15 + c * 0.65) * p.grass;
      setInstance(grass, i, x, groundY(x, z, p) + height / 2, z,
        (0.08 + d * 0.15) * p.grass, height, 0.12 * p.grass, c * Math.PI);
    }
    for (let i = 0; i < 65; i++) {
      const [a, b, c, d] = data[i + 90];
      const z = -b * TILE_LENGTH;
      const gravel = (1 - MathUtils.smoothstep(p.rockScale, 0.25, 0.6)) * (i % 3 === 0 ? 1 : 0);
      const scale = Math.min(0.95, (1 - gravel * 0.7) * (0.15 + c * p.rockScale))
        * MathUtils.clamp((p.rocks - d) * 9, 0, 1);
      // Keep boulders' full footprint outside the path, not just their centre.
      const offset = MathUtils.lerp((i % 2 ? 1 : -1) * (p.width / 2 + scale * 1.4 + 0.4 + a * 16),
        (a - 0.5) * p.width * 0.9, gravel);
      const x = pathX(z, p) + offset;
      setInstance(rocks, i, x, groundY(x, z, p) + scale * 0.25, z, scale * 1.4, scale, scale, c * Math.PI);
    }
    for (let i = 0; i < 38; i++) {
      const [a, b, c, d] = data[i + 150];
      const z = -b * TILE_LENGTH;
      const x = pathX(z, p) + (i % 2 ? 1 : -1) * (p.width / 2 + 0.3 + a * 9);
      const size = (0.35 + c * 0.7) * p.brush;
      const y = groundY(x, z, p);
      setInstance(brush, i, x, y + size * 0.5, z, size, size * 0.7, size, d * Math.PI);
      setInstance(thorns, i, x, y + size, z, size * 0.9, size * 1.2, size * 0.9, d * Math.PI);
    }
    for (let i = 0; i < 16; i++) {
      const [a, b, c] = data[i + 210];
      setInstance(ripples, i, (a - 0.5) * 60, 0.039, -16 + (b - 0.5) * 4 * p.water,
        0.5 + c * 2, 1, 0.018 * p.water);
    }
    for (const ref of [trunks, crowns, pines, grass, rocks, brush, thorns, puddles, ripples]) {
      if (!ref.current) continue;
      ref.current.instanceMatrix.needsUpdate = true;
      ref.current.computeBoundingSphere();
    }
  }, -0.4);

  return (
    <group ref={tile}>
      <mesh ref={groundRef} geometry={groundMeshGeometry} receiveShadow><meshStandardMaterial ref={groundMaterial} roughness={1} /></mesh>
      <mesh ref={pathRef} geometry={pathMeshGeometry} receiveShadow><meshStandardMaterial ref={pathMaterial} roughness={1} /></mesh>
      <instancedMesh ref={trunks} args={[undefined, undefined, 32]} castShadow receiveShadow>
        <cylinderGeometry args={[0.65, 1, 1, 6]} /><meshStandardMaterial color="#695e47" roughness={1} />
      </instancedMesh>
      <instancedMesh ref={crowns} args={[undefined, undefined, 32]} castShadow receiveShadow>
        <icosahedronGeometry args={[1, 1]} /><meshStandardMaterial ref={crownMaterial} roughness={1} flatShading />
      </instancedMesh>
      <instancedMesh ref={pines} args={[undefined, undefined, 32]} castShadow receiveShadow>
        <coneGeometry args={[1, 1, 7]} /><meshStandardMaterial ref={pineMaterial} roughness={1} flatShading />
      </instancedMesh>
      <instancedMesh ref={grass} args={[undefined, undefined, 220]}>
        <coneGeometry args={[1, 1, 3]} /><meshStandardMaterial color="#839466" roughness={1} />
      </instancedMesh>
      <instancedMesh ref={rocks} args={[undefined, undefined, 65]} castShadow receiveShadow>
        <dodecahedronGeometry args={[1, 0]} /><meshStandardMaterial ref={rockMaterial} roughness={1} flatShading />
      </instancedMesh>
      <instancedMesh ref={brush} args={[undefined, undefined, 38]} castShadow>
        <icosahedronGeometry args={[1, 0]} /><meshStandardMaterial ref={brushMaterial} roughness={1} flatShading />
      </instancedMesh>
      <instancedMesh ref={thorns} args={[briars, undefined, 38]}>
        <meshStandardMaterial color="#64533b" roughness={1} />
      </instancedMesh>
      <instancedMesh ref={puddles} args={[puddleGeometry, undefined, 8]} frustumCulled={false}>
        <meshStandardMaterial color="#748d92" metalness={0.35} roughness={0.18} />
      </instancedMesh>
      <mesh ref={creek} position={[0, 0.03, -16]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[70, 5]} /><meshStandardMaterial color="#719ea0" roughness={0.22} metalness={0.2} />
      </mesh>
      <instancedMesh ref={ripples} args={[undefined, undefined, 16]}>
        <boxGeometry args={[1, 0.005, 1]} /><meshStandardMaterial color="#c1d7c4" roughness={0.35} />
      </instancedMesh>
    </group>
  );
}

export function Landscape({ motion, label, atmosphere, snap }: {
  motion: RefObject<SceneMotion>; label?: string; atmosphere: RefObject<AtmosphereState>; snap: boolean;
}) {
  const target = terrainProfile(label);
  const terrain = useRef<TerrainState>({
    profile: { ...target }, ground: new Color(target.ground), trail: new Color(target.trail),
    foliage: new Color(target.foliage), rock: new Color(target.rock), version: 0,
  });
  const colors = useMemo(() => ({ ground: new Color(target.ground), trail: new Color(target.trail),
    foliage: new Color(target.foliage), rock: new Color(target.rock) }), [target]);
  const landscape = useRef<Group>(null);
  useFrame((_, delta) => {
    const current = terrain.current;
    const alpha = snap ? 1 : 1 - Math.exp(-Math.min(delta, 0.05) * 1.6);
    let changed = false;
    for (const key of NUMERIC_KEYS) {
      const difference = target[key] - current.profile[key];
      if (Math.abs(difference) < 0.0001) continue;
      current.profile[key] += difference * alpha;
      changed = true;
    }
    for (const key of ["ground", "trail", "foliage", "rock"] as const) current[key].lerp(colors[key], alpha);
    if (changed) current.version++;
    if (landscape.current) {
      landscape.current.rotation.x = current.profile.slope;
      landscape.current.position.x = -pathX(-motion.current.distance, current.profile);
    }
  }, -0.6);
  return (
    <>
      <group ref={landscape}>
        {Array.from({ length: TILE_COUNT }, (_, index) => (
          <TrailTile key={index} index={index} motion={motion} terrain={terrain} atmosphere={atmosphere} />
        ))}
      </group>
      {Array.from({ length: 11 }, (_, index) => (
        <mesh key={index} position={[(index - 5) * 17, -5, -115 - seeded(index, 20) * 12]} scale={[24, 14 + seeded(index, 21) * 22, 18]}>
          <icosahedronGeometry args={[1, 1]} /><meshStandardMaterial color={index % 2 ? "#6e8176" : "#8b9685"} flatShading roughness={1} />
        </mesh>
      ))}
    </>
  );
}
