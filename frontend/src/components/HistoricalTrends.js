import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const LOCATION_COLORS = {
  "Marathahalli Bridge": "#00bfff",
  "Silk Board": "#ff3333",
  "KR Puram": "#ff8800",
  "Hebbal": "#00ff99",
  "Whitefield": "#ffcc00",
  "Electronic City": "#bb66ff",
};

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div
        style={{
          background: "rgba(10,20,35,0.95)",
          border: "1px solid rgba(255,255,255,0.2)",
          borderRadius: "10px",
          padding: "12px 14px",
          fontSize: "12px",
          color: "#fff",
          minWidth: "180px",
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: "8px", color: "#00bfff" }}>
          {label}
        </div>
        {payload
          .sort((a, b) => b.value - a.value)
          .map((item, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <div
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: item.color,
                }}
              />
              <span style={{ color: "#ddd" }}>{item.name}:</span>
              <strong style={{ color: item.color }}>{item.value}</strong>
            </div>
          ))}
      </div>
    );
  }
  return null;
};

function HistoricalTrends({ trendData, locations, cityTrend }) {
  if (!trendData || trendData.length === 0) {
    return (
      <div style={{ color: "#aaa", textAlign: "center", padding: "40px" }}>
        Loading historical data...
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <div style={{ marginBottom: "10px" }}>
        <div style={{ fontSize: "15px", color: "#ddd", marginBottom: "4px" }}>
          <strong>7-Day Historical Trends</strong>
        </div>
        <div style={{ fontSize: "12px", color: "#aaa" }}>
          Multi-location congestion comparison
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart
          data={trendData}
          margin={{ top: 5, right: 15, left: -5, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#888", fontSize: 11 }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
          />
          <YAxis
            domain={[0, "auto"]}
            tick={{ fill: "#888", fontSize: 11 }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }}
            iconType="circle"
            iconSize={8}
          />
          {locations &&
            locations.map((loc) => (
              <Line
                key={loc}
                type="monotone"
                dataKey={loc}
                stroke={LOCATION_COLORS[loc] || "#aaa"}
                strokeWidth={2}
                dot={{ r: 3, strokeWidth: 0 }}
                activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }}
                name={loc.replace(" Bridge", "")}
              />
            ))}
        </LineChart>
      </ResponsiveContainer>

      {/* City average trend mini-chart */}
      {cityTrend && cityTrend.length > 0 && (
        <div
          style={{
            marginTop: "16px",
            background: "rgba(0,191,255,0.05)",
            border: "1px solid rgba(0,191,255,0.2)",
            borderRadius: "10px",
            padding: "10px",
          }}
        >
          <div style={{ fontSize: "12px", color: "#00bfff", marginBottom: "6px", fontWeight: "bold" }}>
            📊 City-Wide Average Trend
          </div>
          <ResponsiveContainer width="100%" height={60}>
            <LineChart data={cityTrend} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <Line
                type="monotone"
                dataKey="avg"
                stroke="#00bfff"
                strokeWidth={2}
                dot={false}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(0,0,0,0.9)",
                  border: "1px solid #00bfff",
                  borderRadius: "6px",
                  fontSize: "11px",
                }}
                labelStyle={{ color: "#00bfff" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default HistoricalTrends;
