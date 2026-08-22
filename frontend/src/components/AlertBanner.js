import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

function AlertBanner({ hotspots, incidents = [] }) {
  const [alerts, setAlerts] = useState([]);
  const [visible, setVisible] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const safeHotspots = hotspots || [];
    const safeIncidents = incidents || [];

    const congestionAlerts = safeHotspots
      .filter((h) => h.status === "SEVERE" || h.status === "HIGH")
      .map((h) => ({
        id: h.location,
        location: h.location,
        status: h.status,
        congestion: h.congestion,
        message:
          h.status === "SEVERE"
            ? `🚨 SEVERE gridlock at ${h.location} — Congestion index ${h.congestion.toFixed(1)}. Alternate route strongly advised.`
            : `⚠️ HIGH congestion at ${h.location} — Index ${h.congestion.toFixed(1)}. Expect 25-40 min delay.`,
        color: h.status === "SEVERE" ? "#ff3333" : "#ff8800",
      }));

    const incidentAlerts = safeIncidents.map((incident, index) => {
      const severity = (incident.severity || "MODERATE").toUpperCase();
      const isSevere = severity === "SEVERE" || severity === "HIGH";
      return {
        id: `incident-${incident.location_name}-${index}`,
        location: incident.location_name,
        status: severity,
        congestion: null,
        message: `ASTraM ${severity}: ${incident.disruption_type} near ${incident.location_name}. ${incident.description || "Use caution and consider alternate routes."}`,
        color: isSevere ? "#ff3333" : "#ff8800",
      };
    });

    setAlerts([...incidentAlerts, ...congestionAlerts]);
    setCurrentIndex(0);
  }, [hotspots, incidents]);

  // Cycle through alerts every 4 seconds
  useEffect(() => {
    if (alerts.length <= 1) return;
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % alerts.length);
        setVisible(true);
      }, 300);
    }, 4000);
    return () => clearInterval(interval);
  }, [alerts]);

  if (!alerts.length) {
    return (
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          background: "linear-gradient(135deg, rgba(0,255,153,0.12), rgba(0,255,153,0.05))",
          border: "1px solid rgba(0,255,153,0.3)",
          borderRadius: "12px",
          padding: "12px 20px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
          fontSize: "14px",
          color: "#00ff99",
        }}
      >
        <span style={{ fontSize: "18px" }}>✅</span>
        <span>
          <strong>All Clear —</strong> No severe congestion alerts across Bengaluru right now.
        </span>
      </motion.div>
    );
  }

  const current = alerts[currentIndex];

  return (
    <div style={{ position: "relative" }}>
      <AnimatePresence mode="wait">
        {visible && (
          <motion.div
            key={current.id + currentIndex}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            transition={{ duration: 0.3 }}
            style={{
              background: `linear-gradient(135deg, ${current.color}20, ${current.color}08)`,
              border: `1px solid ${current.color}50`,
              borderLeft: `4px solid ${current.color}`,
              borderRadius: "12px",
              padding: "12px 20px",
              display: "flex",
              alignItems: "center",
              gap: "14px",
              fontSize: "14px",
              color: "#ffffff",
            }}
          >
            {/* Pulsing dot */}
            <div style={{ position: "relative", flexShrink: 0 }}>
              <div
                style={{
                  width: "12px",
                  height: "12px",
                  borderRadius: "50%",
                  background: current.color,
                  boxShadow: `0 0 8px ${current.color}`,
                  animation: "alertPulse 1.2s infinite",
                }}
              />
            </div>

            <span style={{ flex: 1 }}>{current.message}</span>

            {/* Alert counter */}
            {alerts.length > 1 && (
              <span
                style={{
                  background: current.color + "30",
                  color: current.color,
                  padding: "2px 8px",
                  borderRadius: "20px",
                  fontSize: "12px",
                  fontWeight: "bold",
                  flexShrink: 0,
                }}
              >
                {currentIndex + 1} / {alerts.length}
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        @keyframes alertPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.5); opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}

export default AlertBanner;
