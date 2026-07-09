"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartResponse } from "@/lib/api";

const PALETTE = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#ec4899",
  "#06b6d4",
  "#a855f7",
  "#ef4444",
  "#84cc16",
];

interface ChartViewProps {
  chart: ChartResponse;
}

export default function ChartView({ chart }: ChartViewProps) {
  const seriesNames = Array.from(
    new Set(chart.data.flatMap((point) => point.series.map((s) => s.name))),
  );

  if (chart.type === "chart:pie") {
    const pieData = chart.data.map((point) => ({
      name: point.x,
      value: point.series[0]?.value ?? 0,
    }));
    return (
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip />
            <Legend />
            <Pie data={pieData} dataKey="value" nameKey="name" outerRadius="70%">
              {pieData.map((_, i) => (
                <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  const flatData = chart.data.map((point) => {
    const row: Record<string, string | number> = { x: point.x };
    for (const s of point.series) row[s.name] = s.value;
    return row;
  });

  if (chart.type === "chart:line") {
    return (
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={flatData}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-zinc-200 dark:stroke-zinc-800" />
            <XAxis dataKey="x" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            {seriesNames.length > 1 && <Legend />}
            {seriesNames.map((name, i) => (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={flatData}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-zinc-200 dark:stroke-zinc-800" />
          <XAxis dataKey="x" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          {seriesNames.length > 1 && <Legend />}
          {seriesNames.map((name, i) => (
            <Bar key={name} dataKey={name} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
