"use client";

import dynamic from "next/dynamic";
import { useIsDark } from "@/lib/use-is-dark";
import { useReducedMotion } from "@/lib/use-reduced-motion";
import { SCHEMA_EDGES, SCHEMA_NODES } from "@/lib/schema-graph-data";

const SchemaGraphScene = dynamic(() => import("@/components/three/SchemaGraphScene"), {
  ssr: false,
});

const VIEW_W = 420;
const VIEW_H = 320;
const SCALE = 46;

function project(position: [number, number, number]): [number, number] {
  return [VIEW_W / 2 + position[0] * SCALE, VIEW_H / 2 - position[1] * SCALE];
}

function StaticSchemaGraph({ dark }: { dark: boolean }) {
  const nodeColor = dark ? "#2aa073" : "#178c60";
  const lineColor = dark ? "#38352f" : "#d8d3c6";
  const positions = new Map(SCHEMA_NODES.map((n) => [n.id, project(n.position)]));

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className="h-full w-full"
      role="img"
      aria-label="Ambient decorative diagram of connected data tables"
    >
      {SCHEMA_EDGES.map((edge) => {
        const from = positions.get(edge.from)!;
        const to = positions.get(edge.to)!;
        return (
          <line
            key={`${edge.from}-${edge.to}`}
            x1={from[0]}
            y1={from[1]}
            x2={to[0]}
            y2={to[1]}
            stroke={lineColor}
            strokeWidth={1}
          />
        );
      })}
      {SCHEMA_NODES.map((node) => {
        const [x, y] = positions.get(node.id)!;
        return <circle key={node.id} cx={x} cy={y} r={5} fill={nodeColor} />;
      })}
    </svg>
  );
}

export default function SchemaGraphBackdrop() {
  const dark = useIsDark();
  const reducedMotion = useReducedMotion();

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-70">
      {reducedMotion ? (
        <StaticSchemaGraph dark={dark} />
      ) : (
        <SchemaGraphScene dark={dark} />
      )}
    </div>
  );
}
