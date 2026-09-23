import { useRef } from "react";
import type { RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { Group, MathUtils } from "three";
import type { SceneMotion } from "./motion";

const SKIN = "#d9a176";
const SHIRT = "#ec9b37";

function Limb({ leg = false }: { leg?: boolean }) {
  return (
    <>
      <mesh position={[0, -0.22, 0]} castShadow>
        <capsuleGeometry args={[leg ? 0.115 : 0.085, 0.29, 4, 8]} />
        <meshStandardMaterial color={leg ? "#303e3b" : SHIRT} roughness={0.9} />
      </mesh>
      {/* Forward is -Z: elbows bend forward (+X), knees bend back (-X). */}
      <group position={[0, -0.43, 0]} rotation={[leg ? -0.3 : 1.05, 0, 0]}>
        <mesh position={[0, -0.19, 0]} castShadow>
          <capsuleGeometry args={[leg ? 0.085 : 0.065, 0.27, 4, 8]} />
          <meshStandardMaterial color={SKIN} roughness={0.85} />
        </mesh>
        <mesh position={[0, -0.4, leg ? -0.075 : 0]} scale={leg ? [0.14, 0.105, 0.25] : [0.08, 0.1, 0.085]} castShadow>
          <sphereGeometry args={[1, 10, 8]} />
          <meshStandardMaterial color={leg ? "#f1e7c9" : SKIN} roughness={0.8} />
        </mesh>
      </group>
    </>
  );
}

export function TrailRunner({ motion }: { motion: RefObject<SceneMotion> }) {
  const body = useRef<Group>(null);
  const leftLeg = useRef<Group>(null);
  const rightLeg = useRef<Group>(null);
  const leftArm = useRef<Group>(null);
  const rightArm = useRef<Group>(null);
  useFrame(() => {
    const { phase, speed, time } = motion.current;
    const amplitude = MathUtils.clamp(speed / 1.5, 0, 1);
    if (body.current) {
      body.current.position.y = 0.03 + Math.abs(Math.sin(phase)) * 0.075 * amplitude;
      body.current.rotation.z = Math.sin(phase) * 0.045 * amplitude;
      body.current.rotation.x = -0.05 * amplitude;
      body.current.scale.y = 1 + Math.sin(time * 2) * 0.003;
    }
    if (leftLeg.current) leftLeg.current.rotation.x = Math.sin(phase) * 0.7 * amplitude;
    if (rightLeg.current) rightLeg.current.rotation.x = -Math.sin(phase) * 0.7 * amplitude;
    if (leftArm.current) leftArm.current.rotation.x = -Math.sin(phase) * 0.65 * amplitude;
    if (rightArm.current) rightArm.current.rotation.x = Math.sin(phase) * 0.65 * amplitude;
  });

  return (
    <group ref={body}>
      <group position={[-0.16, 0.92, 0]} ref={leftLeg}><Limb leg /></group>
      <group position={[0.16, 0.92, 0]} ref={rightLeg}><Limb leg /></group>
      <mesh position={[0, 1.3, 0]} scale={[0.35, 0.46, 0.23]} castShadow>
        <sphereGeometry args={[1, 12, 10]} /><meshStandardMaterial color={SHIRT} roughness={0.9} />
      </mesh>
      <group position={[-0.34, 1.55, 0]} ref={leftArm} rotation={[0, 0, -0.12]}><Limb /></group>
      <group position={[0.34, 1.55, 0]} ref={rightArm} rotation={[0, 0, 0.12]}><Limb /></group>
      <mesh position={[0, 2.03, 0]} scale={[0.43, 0.46, 0.41]} castShadow>
        <sphereGeometry args={[1, 20, 16]} /><meshStandardMaterial color={SKIN} roughness={0.8} />
      </mesh>
      {/* Cap and brim face down the trail (-Z). */}
      <mesh position={[0, 2.27, 0.01]} scale={[0.445, 0.27, 0.43]} castShadow>
        <sphereGeometry args={[1, 16, 10]} /><meshStandardMaterial color="#c75b38" roughness={0.9} />
      </mesh>
      <mesh position={[0, 2.26, -0.37]} scale={[0.4, 0.035, 0.31]} castShadow>
        <sphereGeometry args={[1, 12, 8]} /><meshStandardMaterial color="#c75b38" roughness={0.9} />
      </mesh>
      <mesh position={[0, 1.38, 0.23]} scale={[0.255, 0.33, 0.14]} castShadow>
        <sphereGeometry args={[1, 10, 8]} /><meshStandardMaterial color="#286569" roughness={0.95} />
      </mesh>
      <mesh position={[0, 1.37, 0.365]}>
        <boxGeometry args={[0.06, 0.32, 0.015]} /><meshStandardMaterial color="#bdd7bb" roughness={0.9} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * 0.25, 1.32, 0.25]} rotation={[0, 0, side * -0.15]} castShadow>
          <capsuleGeometry args={[0.055, 0.2, 4, 8]} /><meshStandardMaterial color="#c6d6c7" roughness={0.8} />
        </mesh>
      ))}
    </group>
  );
}
