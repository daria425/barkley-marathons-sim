import { useLayoutEffect, useRef } from "react";
import type { RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, Group, InstancedMesh, Object3D } from "three";
import type { SceneMotion } from "./motion";

const TILE_LENGTH = 32;
const TILE_COUNT = 5;

// Stable decoration, independent of render count and the simulation's RNG.
function random(index: number, salt: number) {
  const n = Math.sin(index * 127.1 + salt * 311.7) * 43758.5453;
  return n - Math.floor(n);
}

function TrailTile({ index, motion }: { index: number; motion: RefObject<SceneMotion> }) {
  const tile = useRef<Group>(null);
  const trunks = useRef<InstancedMesh>(null);
  const crowns = useRef<InstancedMesh>(null);
  const grass = useRef<InstancedMesh>(null);
  const rocks = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    const object = new Object3D();
    const color = new Color();
    for (let i = 0; i < 28; i++) {
      const seed = index * 100 + i;
      const side = i % 2 ? 1 : -1;
      const x = side * (3.6 + random(seed, 1) * 19);
      const z = -random(seed, 2) * TILE_LENGTH;
      const height = 3.5 + random(seed, 3) * 5.5;
      object.position.set(x, height / 2, z);
      object.scale.set(0.16 + height * 0.018, height, 0.16 + height * 0.018);
      object.updateMatrix();
      trunks.current?.setMatrixAt(i, object.matrix);
      object.position.y = height * 0.8;
      object.scale.set(height * 0.32, height * 0.48, height * 0.32);
      object.rotation.y = random(seed, 5) * Math.PI;
      object.updateMatrix();
      crowns.current?.setMatrixAt(i, object.matrix);
      color.set(["#496750", "#5d7752", "#738259", "#3f6152"][i % 4]);
      crowns.current?.setColorAt(i, color);
    }
    for (let i = 0; i < 350; i++) {
      const seed = index * 500 + i;
      object.position.set((i % 2 ? 1 : -1) * (2.05 + random(seed, 7) * 15), 0.12, -random(seed, 8) * TILE_LENGTH);
      object.scale.set(0.09 + random(seed, 9) * 0.15, 0.18 + random(seed, 10) * 0.32, 0.09);
      object.rotation.set(0, random(seed, 11) * Math.PI, (random(seed, 12) - 0.5) * 0.4);
      object.updateMatrix();
      grass.current?.setMatrixAt(i, object.matrix);
      color.set(["#82936a", "#9b9e6a", "#607c55"][i % 3]);
      grass.current?.setColorAt(i, color);
    }
    for (let i = 0; i < 28; i++) {
      const seed = index * 50 + i;
      const scale = 0.12 + random(seed, 13) * 0.7;
      object.position.set((i % 2 ? 1 : -1) * (2.05 + random(seed, 14) * 9), scale * 0.22, -random(seed, 15) * TILE_LENGTH);
      object.scale.set(scale * 1.4, scale * 0.8, scale);
      object.rotation.set(random(seed, 16), random(seed, 17), 0);
      object.updateMatrix();
      rocks.current?.setMatrixAt(i, object.matrix);
    }
    for (const ref of [trunks, crowns, grass, rocks]) {
      if (ref.current) {
        ref.current.instanceMatrix.needsUpdate = true;
        if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true;
        ref.current.computeBoundingSphere();
      }
    }
  }, [index]);
  useFrame(() => {
    if (tile.current) tile.current.position.z = ((motion.current.distance + index * TILE_LENGTH) % (TILE_COUNT * TILE_LENGTH)) - (TILE_COUNT - 1) * TILE_LENGTH + 16;
  });
  return (
    <group ref={tile} position={[0, 0, index * TILE_LENGTH - 112]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.025, -TILE_LENGTH / 2]} receiveShadow>
        <planeGeometry args={[70, TILE_LENGTH]} /><meshStandardMaterial color="#718263" roughness={1} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, -TILE_LENGTH / 2]} receiveShadow>
        <planeGeometry args={[4.2, TILE_LENGTH]} /><meshStandardMaterial color="#bca580" roughness={1} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.003, -TILE_LENGTH / 2]} receiveShadow>
        <planeGeometry args={[2.9, TILE_LENGTH]} /><meshStandardMaterial color="#c8b38f" roughness={1} />
      </mesh>
      <instancedMesh ref={trunks} args={[undefined, undefined, 28]} castShadow receiveShadow>
        <cylinderGeometry args={[0.65, 1, 1, 6]} /><meshStandardMaterial color="#695e47" roughness={1} />
      </instancedMesh>
      <instancedMesh ref={crowns} args={[undefined, undefined, 28]} castShadow receiveShadow>
        <icosahedronGeometry args={[1, 1]} /><meshStandardMaterial roughness={1} flatShading />
      </instancedMesh>
      <instancedMesh ref={grass} args={[undefined, undefined, 350]}>
        <coneGeometry args={[1, 1, 3]} /><meshStandardMaterial roughness={1} />
      </instancedMesh>
      <instancedMesh ref={rocks} args={[undefined, undefined, 28]} castShadow receiveShadow>
        <dodecahedronGeometry args={[1, 0]} /><meshStandardMaterial color="#89887a" roughness={1} flatShading />
      </instancedMesh>
    </group>
  );
}

export function Landscape({ motion }: { motion: RefObject<SceneMotion> }) {
  return (
    <>
      {Array.from({ length: TILE_COUNT }, (_, index) => <TrailTile key={index} index={index} motion={motion} />)}
      {Array.from({ length: 11 }, (_, index) => (
        <mesh key={index} position={[(index - 5) * 17, 0, -105 - random(index, 20) * 20]} scale={[24, 14 + random(index, 21) * 22, 18]}>
          <icosahedronGeometry args={[1, 1]} /><meshStandardMaterial color={index % 2 ? "#6e8176" : "#8b9685"} flatShading roughness={1} />
        </mesh>
      ))}
    </>
  );
}
