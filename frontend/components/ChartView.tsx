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

// Fixed categorical order, validated for CVD-safety and contrast against
// both the light (Paper) and dark (Ink) surfaces via the dataviz skill's
// validator. Referenced as CSS variables so the chart follows the active
// theme instead of a second, hardcoded color set.
const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
];

const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
  fontSize: "13px",
  fontFamily: "var(--font-sans)",
  color: "var(--popover-foreground)",
};

// Recharts sizes the YAxis label gutter off the tick font, so raw
// 8-digit values ("16000000") clip against the chart edge at the larger
// type scale. Abbreviating also just reads better.
function formatAxisNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(abs % 1_000_000 === 0 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs % 1_000 === 0 ? 0 : 1)}K`;
  return `${value}`;
}

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
      <div className="h-64 w-full sm:h-72 lg:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 13, fontFamily: "var(--font-sans)" }} />
            <Pie data={pieData} dataKey="value" nameKey="name" outerRadius="70%">
              {pieData.map((_, i) => (
                <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
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
      <div className="h-64 w-full sm:h-72 lg:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={flatData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="x"
              tick={{ fontSize: 13, fill: "var(--muted-foreground)" }}
              stroke="var(--border)"
            />
            <YAxis tick={{ fontSize: 13, fill: "var(--muted-foreground)" }} stroke="var(--border)" tickFormatter={formatAxisNumber} width={48} />
            <Tooltip contentStyle={tooltipStyle} />
            {seriesNames.length > 1 && (
              <Legend wrapperStyle={{ fontSize: 13, fontFamily: "var(--font-sans)" }} />
            )}
            {seriesNames.map((name, i) => (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={CHART_COLORS[i % CHART_COLORS.length]}
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
    <div className="h-64 w-full sm:h-72 lg:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={flatData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="x"
            tick={{ fontSize: 13, fill: "var(--muted-foreground)" }}
            stroke="var(--border)"
          />
          <YAxis tick={{ fontSize: 13, fill: "var(--muted-foreground)" }} stroke="var(--border)" tickFormatter={formatAxisNumber} width={48} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--muted)" }} />
          {seriesNames.length > 1 && (
            <Legend wrapperStyle={{ fontSize: 13, fontFamily: "var(--font-sans)" }} />
          )}
          {seriesNames.map((name, i) => (
            <Bar key={name} dataKey={name} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
