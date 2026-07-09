export interface SchemaNode {
  id: string;
  position: [number, number, number];
}

export interface SchemaEdge {
  from: string;
  to: string;
  joinKey: string;
}

export const SCHEMA_NODES: SchemaNode[] = [
  { id: "customers", position: [-2.4, 1.1, 0.4] },
  { id: "orders", position: [0, 0, 0] },
  { id: "order_items", position: [2.3, 0.6, -0.6] },
  { id: "products", position: [3.6, -1.2, 0.8] },
  { id: "payment", position: [-1.1, -1.8, -0.9] },
  { id: "shipments", position: [1.2, -2.1, 1.1] },
  { id: "reviews", position: [-2.6, -0.6, 1.6] },
  { id: "suppliers", position: [5.2, -0.2, -0.4] },
];

export const SCHEMA_EDGES: SchemaEdge[] = [
  { from: "customers", to: "orders", joinKey: "customer_id" },
  { from: "orders", to: "order_items", joinKey: "order_id" },
  { from: "orders", to: "payment", joinKey: "order_id" },
  { from: "orders", to: "shipments", joinKey: "order_id" },
  { from: "order_items", to: "products", joinKey: "product_id" },
  { from: "products", to: "suppliers", joinKey: "supplier_id" },
  { from: "products", to: "reviews", joinKey: "product_id" },
  { from: "customers", to: "reviews", joinKey: "customer_id" },
];
