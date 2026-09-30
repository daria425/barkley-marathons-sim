import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { DoubleSide, Group } from "three";
import type { EndStatus } from "@/lib/raceOutcome";

function Confetti() {
  const group = useRef<Group>(null);
  const elapsed = useRef(0);
  useFrame((_, delta) => {
    elapsed.current += Math.min(delta, 0.05);
    if (!group.current) return;
    group.current.visible = elapsed.current < 5;
    group.current.children.forEach((piece, index) => {
      const t = elapsed.current;
      const angle = index * 2.4;
      piece.position.set(Math.cos(angle) * (0.4 + t * 0.4), 3.4 + (index % 7) * 0.14 - t * 0.8, Math.sin(angle) * (0.4 + t * 0.4));
      piece.rotation.set(t * 2 + index, t + index, t * 1.4);
    });
  });
  return (
    <group ref={group}>
      {Array.from({ length: 42 }, (_, i) => <mesh key={i}>
        <planeGeometry args={[0.07, 0.12]} />
        <meshStandardMaterial side={DoubleSide} color={["#f5cf73", "#a7dabc", "#ef9772"][i % 3]} />
      </mesh>)}
    </group>
  );
}

export function EndSceneProps({ status }: { status: EndStatus }) {
  if (status === "finished") return (
    <>
      <group position={[0, 0, -1.5]}>
        {[-2.3, 2.3].map((x) => <mesh key={x} position={[x, 1.65, 0]} castShadow>
          <cylinderGeometry args={[0.055, 0.075, 3.3, 8]} /><meshStandardMaterial color="#70523a" />
        </mesh>)}
        <mesh position={[0, 2.95, 0]} castShadow><boxGeometry args={[4.6, 0.52, 0.055]} /><meshStandardMaterial color="#f4e9c8" /></mesh>
        {Array.from({ length: 18 }, (_, i) => <mesh key={i} position={[-2.17 + i * 0.255, 2.95 + (i % 2 ? 0.13 : -0.13), 0.031]}>
          <planeGeometry args={[0.255, 0.26]} /><meshStandardMaterial color="#304a3b" />
        </mesh>)}
      </group>
      <Confetti />
    </>
  );
  if (status === "dnf_cutoff") return (
    <group position={[1.6, 0, -0.5]} rotation={[0, 0.3, 0]}>
      <mesh position={[0, 0.65, 0]} castShadow><boxGeometry args={[0.09, 1.3, 0.09]} /><meshStandardMaterial color="#70523a" /></mesh>
      <group position={[0, 1.5, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <mesh castShadow><cylinderGeometry args={[0.4, 0.4, 0.13, 32]} /><meshStandardMaterial color="#b88f52" /></mesh>
        <mesh position={[0, 0.072, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[0.35, 32]} /><meshStandardMaterial color="#f3e4c4" /></mesh>
      </group>
      <mesh position={[0, 1.61, 0.09]}><boxGeometry args={[0.035, 0.24, 0.025]} /><meshStandardMaterial color="#514333" /></mesh>
      <mesh position={[0.1, 1.5, 0.09]}><boxGeometry args={[0.23, 0.035, 0.025]} /><meshStandardMaterial color="#514333" /></mesh>
    </group>
  );
  return (
    <mesh position={[0, 0.28, -0.2]} scale={[0.68, 0.35, 0.46]} rotation={[0, 0.3, 0]} castShadow receiveShadow>
      <dodecahedronGeometry args={[1, 1]} /><meshStandardMaterial color="#808679" roughness={1} flatShading />
    </mesh>
  );
}
