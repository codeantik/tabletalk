"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { SCHEMA_EDGES, SCHEMA_NODES } from "@/lib/schema-graph-data";

const LIGHT_NODE_COLORS = [
  "#178c60",
  "#a9803a",
  "#1f6e9c",
  "#a83e2e",
  "#7a4a9c",
  "#a83e70",
  "#178c60",
  "#a9803a",
];

const DARK_NODE_COLORS = [
  "#2aa073",
  "#c2801e",
  "#4f94c7",
  "#c05a45",
  "#9a6bc0",
  "#c05a8c",
  "#2aa073",
  "#c2801e",
];

function Graph({ dark }: { dark: boolean }) {
  const group = useRef<THREE.Group>(null);
  const nodeColors = dark ? DARK_NODE_COLORS : LIGHT_NODE_COLORS;
  const lineColor = dark ? "#38352f" : "#d8d3c6";

  const positions = useMemo(() => {
    const map = new Map<string, [number, number, number]>();
    for (const n of SCHEMA_NODES) map.set(n.id, n.position);
    return map;
  }, []);

  const edgeGeometry = useMemo(() => {
    return SCHEMA_EDGES.map((edge) => {
      const from = positions.get(edge.from)!;
      const to = positions.get(edge.to)!;
      const geometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(...from),
        new THREE.Vector3(...to),
      ]);
      return { key: `${edge.from}-${edge.to}`, geometry };
    });
  }, [positions]);

  useFrame((state) => {
    if (!group.current) return;
    const t = state.clock.getElapsedTime();
    group.current.rotation.y = t * 0.05;
    group.current.rotation.x = Math.sin(t * 0.08) * 0.08;
  });

  return (
    <group ref={group}>
      {edgeGeometry.map(({ key, geometry }) => (
        <primitive
          key={key}
          object={new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: lineColor, transparent: true, opacity: 0.5 }))}
        />
      ))}
      {SCHEMA_NODES.map((node, i) => (
        <Node key={node.id} position={node.position} color={nodeColors[i % nodeColors.length]} phase={i} />
      ))}
    </group>
  );
}

function Node({
  position,
  color,
  phase,
}: {
  position: [number, number, number];
  color: string;
  phase: number;
}) {
  const mesh = useRef<THREE.Mesh>(null);
  const base = useMemo(() => new THREE.Vector3(...position), [position]);

  useFrame((state) => {
    if (!mesh.current) return;
    const t = state.clock.getElapsedTime();
    mesh.current.position.y = base.y + Math.sin(t * 0.6 + phase) * 0.15;
  });

  return (
    <mesh ref={mesh} position={position}>
      <sphereGeometry args={[0.14, 16, 16]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} roughness={0.4} />
    </mesh>
  );
}

export default function SchemaGraphScene({ dark }: { dark: boolean }) {
  return (
    <Canvas
      camera={{ position: [0, 0.5, 7.5], fov: 45 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: true }}
    >
      <ambientLight intensity={dark ? 0.5 : 0.8} />
      <pointLight position={[5, 5, 5]} intensity={dark ? 0.6 : 0.4} />
      <Graph dark={dark} />
    </Canvas>
  );
}
