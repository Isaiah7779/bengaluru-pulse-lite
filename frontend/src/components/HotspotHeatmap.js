import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
  LabelList,
} from "recharts";
import { motion } from "framer-motion";

const STATUS_COLORS = {
  LOW:      "#00ff99",
  MODERATE: "#ffcc00",
  HIGH:     "#ff8800",
  SEVERE:   "#ff3333",
};

const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const d = payload[0].payload;
    const color = STATUS_COLORS[d.status] || "#aaa";
    return (
      <div
        style={{
          background: "rgba(10,20,35,0.95)",
          border: `1px solid ${color}40`,
          borderRadius: "12px",
          padding: "12px 16px",
          fontSize: "13px",
          color: "#fff",
          minWidth: "180px",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "6px", color }}>
          {d.location}
        </div>
        <div>Congestion: <strong style={{ color }}>{d.congestion.toFixed(1)}</strong></div>
        <div>Status: <strong style={{ color }}>{d.status}</strong></div>
        <div style={{ color: "#aaa", marginTop: "4px", fontSize: "12px" }}>
          {d.is_peak_hour ? "⚡ Currently peak hour" : "Normal traffic period"}
        </div>
      </div>
    );
  }
  return null;
};

const CustomLabel = ({ x, y, width, value, status }) => {
  const color = STATUS_COLORS[status] || "#aaa";
  return (
    <text
      x={x + width + 6}
      y={y + 13}
      fill={color}
      fontSize={11}
      fontWeight="bold"
    >
      {value}
    </text>
  );
};

function HotspotHeatmap({ hotspots, cityAverage }) {
  if (!hotspots || hotspots.length === 0) {
    return (
      <div style={{ color: "#aaa", textAlign: "center", padding: "40px" }}>
        Loading hotspot data...
      </div>
    );
  }

  // Shorten location names for chart
  const data = hotspots.map((h) => ({
    ...h,
    shortName: h.location.replace(" Bridge", "").replace("Electronic ", "E. "),
  }));

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 5, right: 55, left: 10, bottom: 5 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(255,255,255,0.06)"
            horizontal={false}
          />
          <XAxis
            type="number"
            domain={[0, 30]}
            tick={{ fill: "#888", fontSize: 11 }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="shortName"
            tick={{ fill: "#ccc", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={110}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <ReferenceLine
            x={cityAverage || 0}
            stroke="rgba(0,191,255,0.6)"
            strokeDasharray="4 4"
            label={{
              value: `City avg ${(cityAverage || 0).toFixed(1)}`,
              fill: "#00bfff",
              fontSize: 11,
              position: "top",
            }}
          />
          <Bar dataKey="congestion" radius={[0, 6, 6, 0]} maxBarSize={24}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={STATUS_COLORS[entry.status]}
                opacity={0.85}
              />
            ))}
            <LabelList
              dataKey="congestion"
              content={(props) => (
                <CustomLabel
                  {...props}
                  status={data[props.index]?.status}
                  value={data[props.index]?.congestion?.toFixed(1)}
                />
              )}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Rank badges */}
      <div
        style={{
          display: "flex",
          gap: "10px",
          flexWrap: "wrap",
          marginTop: "8px",
        }}
      >
        {data.slice(0, 3).map((h, i) => {
          const color = STATUS_COLORS[h.status];
          const medals = ["🥇", "🥈", "🥉"];
          return (
            <motion.div
              key={h.location}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              style={{
                background: `${color}15`,
                border: `1px solid ${color}40`,
                borderRadius: "8px",
                padding: "4px 10px",
                fontSize: "12px",
                color,
              }}
            >
              {medals[i]} {h.location}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

export default HotspotHeatmap;
