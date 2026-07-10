export interface SchemaNode {
  id: string;
  position: [number, number, number];
}

export interface SchemaEdge {
  from: string;
  to: string;
  joinKey: string;
}

// Purely decorative ambient graphic shown before any CSV is uploaded, so it
// has no real schema to reflect. Generated deterministically instead of
// hand-authored, so it never implies a specific fixed table/column layout.
const NODE_COUNT = 8;
const RADIUS = 2.6;
const SEED = 1;
const JOIN_KEYS = ["id", "ref_id", "key", "parent_id"];

function mulberry32(seed: number) {
  let state = seed | 0;
  return function random() {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function fibonacciSphere(count: number, radius: number): [number, number, number][] {
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const points: [number, number, number][] = [];
  for (let i = 0; i < count; i++) {
    const y = count > 1 ? 1 - (i / (count - 1)) * 2 : 0;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = goldenAngle * i;
    points.push([Math.cos(theta) * r * radius, y * radius * 0.7, Math.sin(theta) * r * radius]);
  }
  return points;
}

function generateSchemaGraph(nodeCount: number, seed: number): { nodes: SchemaNode[]; edges: SchemaEdge[] } {
  const random = mulberry32(seed);
  const nodes: SchemaNode[] = fibonacciSphere(nodeCount, RADIUS).map((position, i) => ({
    id: `table_${i + 1}`,
    position,
  }));

  const edges: SchemaEdge[] = [];
  const connected = [nodes[0]];
  const remaining = nodes.slice(1).sort(() => random() - 0.5);
  for (const node of remaining) {
    const anchor = connected[Math.floor(random() * connected.length)];
    edges.push({ from: anchor.id, to: node.id, joinKey: JOIN_KEYS[Math.floor(random() * JOIN_KEYS.length)] });
    connected.push(node);
  }

  const extraEdgeCount = Math.floor(nodeCount / 3);
  for (let i = 0; i < extraEdgeCount; i++) {
    const a = nodes[Math.floor(random() * nodes.length)];
    const b = nodes[Math.floor(random() * nodes.length)];
    const exists = edges.some(
      (e) => (e.from === a.id && e.to === b.id) || (e.from === b.id && e.to === a.id),
    );
    if (a.id !== b.id && !exists) {
      edges.push({ from: a.id, to: b.id, joinKey: JOIN_KEYS[Math.floor(random() * JOIN_KEYS.length)] });
    }
  }

  return { nodes, edges };
}

const generated = generateSchemaGraph(NODE_COUNT, SEED);
export const SCHEMA_NODES: SchemaNode[] = generated.nodes;
export const SCHEMA_EDGES: SchemaEdge[] = generated.edges;
