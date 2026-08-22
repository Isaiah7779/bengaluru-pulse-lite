import React from "react";
import {
  RadialBarChart,
  RadialBar,
  PolarAngleAxis,
  ResponsiveContainer,
} from "recharts";
import { motion } from "framer-motion";

const STATUS_CONFIG = {
  LOW:      { color: "#00ff99", label: "LOW",      emoji: "🟢" },
  MODERATE: { color: "#ffcc00", label: "MODERATE", emoji: "🟡" },
  HIGH:     { color: "#ff8800", label: "HIGH",     emoji: "🟠" },
  SEVERE:   { color: "#ff3333", label: "SEVERE",   emoji: "🔴" },
};

function getStatus(value) {
  if (value < 8)  return "LOW";
  if (value < 15) return "MODERATE";
  if (value < 22) return "HIGH";
  return "SEVERE";
}

function CongestionGauge({ value = 0, size = 220 }) {
  const clamped = Math.max(0, Math.min(value, 30));
  const percent = (clamped / 30) * 100;
  const status = getStatus(clamped);
  const { color, label, emoji } = STATUS_CONFIG[status];

  const data = [{ value: percent, fill: color }];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        position: "relative",
        width: size,
        height: size,
      }}
    >
      <ResponsiveContainer width={size} height={size}>
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="62%"
          outerRadius="90%"
          startAngle={200}
          endAngle={-20}
          data={data}
          barSize={18}
        >
          {/* Background track */}
          <RadialBar
            dataKey="value"
            cornerRadius={10}
            background={{ fill: "rgba(255,255,255,0.06)" }}
            clockWise
          />
          <PolarAngleAxis
            type="number"
            domain={[0, 100]}
            angleAxisId={0}
            tick={false}
          />
        </RadialBarChart>
      </ResponsiveContainer>

      {/* Center text overlay */}
      <motion.div
        key={clamped}
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 15 }}
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -52%)",
          textAlign: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            fontSize: size * 0.22,
            fontWeight: "900",
            color,
            lineHeight: 1,
            fontFamily: "'Arial', sans-serif",
            textShadow: `0 0 20px ${color}60`,
          }}
        >
          {clamped > 0 ? clamped.toFixed(1) : "--"}
        </div>
        <div
          style={{
            fontSize: size * 0.065,
            color: "#aaaaaa",
            marginTop: "2px",
            letterSpacing: "1px",
          }}
        >
          / 30 INDEX
        </div>
        <div
          style={{
            fontSize: size * 0.078,
            color,
            fontWeight: "700",
            marginTop: "6px",
            letterSpacing: "2px",
          }}
        >
          {emoji} {label}
        </div>
      </motion.div>

      {/* Tick marks */}
      <svg
        style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
        width={size}
        height={size}
      >
        {[0, 8, 15, 22, 30].map((tick) => {
          const angle = 200 - (tick / 30) * 220;
          const rad = (angle * Math.PI) / 180;
          const cx = size / 2;
          const cy = size / 2;
          const r1 = size * 0.46;
          const r2 = size * 0.5;
          return (
            <line
              key={tick}
              x1={cx + r1 * Math.cos(rad)}
              y1={cy - r1 * Math.sin(rad)}
              x2={cx + r2 * Math.cos(rad)}
              y2={cy - r2 * Math.sin(rad)}
              stroke="rgba(255,255,255,0.3)"
              strokeWidth="2"
            />
          );
        })}
      </svg>
    </div>
  );
}

export default CongestionGauge;
