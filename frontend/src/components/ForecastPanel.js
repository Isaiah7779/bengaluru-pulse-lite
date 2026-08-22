import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from "recharts";

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
          borderRadius: "10px",
          padding: "10px 14px",
          fontSize: "12px",
          color: "#fff",
        }}
      >
        <div style={{ fontWeight: "bold", color, marginBottom: "4px" }}>
          {d.label}
        </div>
        <div>Congestion: <strong style={{ color }}>{d.congestion.toFixed(1)}</strong></div>
        <div>Status: <strong style={{ color }}>{d.status}</strong></div>
        {d.hours_ahead === 0 && (
          <div style={{ color: "#00bfff", marginTop: "4px", fontSize: "11px" }}>
            ⏱ Current reading
          </div>
        )}
      </div>
    );
  }
  return null;
};

function ForecastPanel({ forecast, location, peakCongestion, bestWindow }) {
  if (!forecast || forecast.length === 0) {
    return (
      <div style={{ color: "#aaa", textAlign: "center", padding: "40px" }}>
        Loading forecast data...
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <div style={{ marginBottom: "12px" }}>
        <div style={{ fontSize: "15px", color: "#ddd", marginBottom: "4px" }}>
          <strong>12-Hour Forecast</strong> — {location}
        </div>
        <div style={{ fontSize: "13px", color: "#aaa" }}>
          Peak at <span style={{ color: "#ff8800" }}>{peakCongestion?.label || "N/A"}</span>
          {" • "}
          Best travel: <span style={{ color: "#00ff99" }}>{bestWindow?.label || "N/A"}</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <AreaChart
          data={forecast}
          margin={{ top: 10, right: 15, left: -5, bottom: 5 }}
        >
          <defs>
            <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00bfff" stopOpacity={0.6} />
              <stop offset="95%" stopColor="#00bfff" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="label"
            tick={{ fill: "#888", fontSize: 10 }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 30]}
            tick={{ fill: "#888", fontSize: 10 }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          
          {/* Severity bands */}
          <ReferenceLine y={8} stroke="#00ff99" strokeDasharray="2 2" strokeOpacity={0.3} />
          <ReferenceLine y={15} stroke="#ffcc00" strokeDasharray="2 2" strokeOpacity={0.3} />
          <ReferenceLine y={22} stroke="#ff8800" strokeDasharray="2 2" strokeOpacity={0.3} />

          {/* Highlight peak */}
          {peakCongestion && (
            <ReferenceDot
              x={peakCongestion.label}
              y={peakCongestion.congestion}
              r={5}
              fill="#ff3333"
              stroke="#ffffff"
              strokeWidth={2}
            />
          )}

          {/* Highlight best window */}
          {bestWindow && (
            <ReferenceDot
              x={bestWindow.label}
              y={bestWindow.congestion}
              r={5}
              fill="#00ff99"
              stroke="#ffffff"
              strokeWidth={2}
            />
          )}

          <Area
            type="monotone"
            dataKey="congestion"
            stroke="#00bfff"
            strokeWidth={2.5}
            fill="url(#forecastGradient)"
            activeDot={{ r: 6, fill: "#00bfff", stroke: "#fff", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Summary cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "10px",
          marginTop: "12px",
        }}
      >
        <div
          style={{
            background: "rgba(255,136,0,0.1)",
            border: "1px solid rgba(255,136,0,0.3)",
            borderRadius: "8px",
            padding: "8px 12px",
            fontSize: "12px",
          }}
        >
          <div style={{ color: "#aaa" }}>Peak Congestion</div>
          <div style={{ color: "#ff8800", fontWeight: "bold", fontSize: "16px", marginTop: "2px" }}>
            {peakCongestion?.label || "N/A"} • {peakCongestion?.congestion?.toFixed(1) || "--"}
          </div>
        </div>
        <div
          style={{
            background: "rgba(0,255,153,0.1)",
            border: "1px solid rgba(0,255,153,0.3)",
            borderRadius: "8px",
            padding: "8px 12px",
            fontSize: "12px",
          }}
        >
          <div style={{ color: "#aaa" }}>Best Travel Window</div>
          <div style={{ color: "#00ff99", fontWeight: "bold", fontSize: "16px", marginTop: "2px" }}>
            {bestWindow?.label || "N/A"} • {bestWindow?.congestion?.toFixed(1) || "--"}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ForecastPanel;
