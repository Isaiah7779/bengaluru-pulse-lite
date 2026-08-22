import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { FaClock, FaMapMarkerAlt, FaRoute } from "react-icons/fa";
import { API_BASE_URL, STATUS_COLORS } from "../config";

const ROUTE_LABELS = {
  Expressway: "Road",
  "Toll Road": "Toll",
  "Public Transit": "Metro",
};

function CommuteAdvisor({ locations = [] }) {
  const [origin, setOrigin] = useState("Whitefield");
  const [destination, setDestination] = useState("Electronic City");
  const [arrivalTime, setArrivalTime] = useState("09:00");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (locations.length > 0) {
      setOrigin(locations[0]);
      setDestination(locations[1] || locations[0]);
    }
  }, [locations]);

  const fetchAdvice = async () => {
    if (origin === destination) {
      alert("Origin and destination must be different");
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${API_BASE_URL}/commute-advisor`, {
        origin,
        destination,
        preferred_arrival: arrivalTime,
      });
      setResult(response.data);
    } catch (error) {
      console.error(error);
      alert("Failed to fetch commute advice");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ marginBottom: "16px" }}>
        <div style={{ fontSize: "15px", color: "#ddd", marginBottom: "4px" }}>
          <FaRoute style={{ marginRight: "6px" }} />
          <strong>AI Commute Advisor</strong>
        </div>
        <div style={{ fontSize: "12px", color: "#aaa" }}>
          Get optimal departure time and route recommendations
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "16px" }}>
        <div>
          <label style={labelStyle}>
            <FaMapMarkerAlt style={{ color: "#00bfff" }} /> Origin
          </label>
          <select value={origin} onChange={(event) => setOrigin(event.target.value)} style={selectStyle}>
            {locations.map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label style={labelStyle}>
            <FaMapMarkerAlt style={{ color: "#ff3333" }} /> Destination
          </label>
          <select
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            style={selectStyle}
          >
            {locations.map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ marginBottom: "16px" }}>
        <label style={labelStyle}>
          <FaClock /> Preferred Arrival Time
        </label>
        <input
          type="time"
          value={arrivalTime}
          onChange={(event) => setArrivalTime(event.target.value)}
          style={inputStyle}
        />
      </div>

      <button onClick={fetchAdvice} disabled={loading} style={buttonStyle}>
        {loading ? "Analyzing..." : "Get Commute Advice"}
      </button>

      {result && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ marginTop: "16px", flex: 1, overflowY: "auto" }}
        >
          <div style={summaryStyle}>
            <strong style={{ color: "#00bfff" }}>Recommendation:</strong>
            <br />
            {result.advisory}
          </div>

          <div style={{ marginBottom: "12px" }}>
            <div style={sectionTitleStyle}>Departure Time Options</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {result.departure_suggestions?.map((suggestion, index) => {
                const color = STATUS_COLORS[suggestion.status] || "#aaa";
                return (
                  <motion.div
                    key={suggestion.departure_time}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    style={{
                      background: suggestion.recommended ? `${color}15` : "rgba(255,255,255,0.03)",
                      border: suggestion.recommended
                        ? `2px solid ${color}`
                        : "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "8px",
                      padding: "10px 12px",
                      fontSize: "12px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ color, fontWeight: "bold", fontSize: "14px" }}>
                        {suggestion.departure_time}
                      </div>
                      <div style={{ color: "#aaa", fontSize: "11px", marginTop: "2px" }}>
                        {suggestion.estimated_travel_minutes} min | {suggestion.status}
                      </div>
                    </div>
                    {suggestion.recommended && <div style={bestBadgeStyle}>BEST</div>}
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div>
            <div style={sectionTitleStyle}>Route Alternatives</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {result.route_alternatives?.map((route) => (
                <div key={route.route} style={routeCardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
                    <span style={{ fontSize: "12px", color: "#00bfff", fontWeight: "bold" }}>
                      {ROUTE_LABELS[route.type] || "Route"}
                    </span>
                    <strong style={{ color: "#ddd" }}>{route.route}</strong>
                    <span style={routeTypeStyle}>{route.type}</span>
                  </div>
                  <div style={{ color: "#aaa", fontSize: "11px" }}>
                    Delay: {route.typical_delay} | Best for: {route.recommended_for}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

const labelStyle = {
  fontSize: "12px",
  color: "#aaa",
  display: "block",
  marginBottom: "4px",
};

const selectStyle = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(255,255,255,0.15)",
  background: "rgba(255,255,255,0.05)",
  color: "#fff",
  fontSize: "13px",
  outline: "none",
};

const inputStyle = {
  ...selectStyle,
};

const buttonStyle = {
  width: "100%",
  padding: "10px",
  borderRadius: "8px",
  border: "none",
  background: "linear-gradient(135deg, #00bfff, #0080ff)",
  color: "#fff",
  fontSize: "13px",
  fontWeight: "bold",
  cursor: "pointer",
};

const summaryStyle = {
  background: "rgba(0,191,255,0.1)",
  border: "1px solid rgba(0,191,255,0.3)",
  borderRadius: "10px",
  padding: "12px",
  marginBottom: "12px",
  fontSize: "13px",
  color: "#ddd",
};

const sectionTitleStyle = {
  fontSize: "13px",
  color: "#ddd",
  marginBottom: "8px",
  fontWeight: "bold",
};

const bestBadgeStyle = {
  background: "#00ff99",
  color: "#000",
  padding: "2px 8px",
  borderRadius: "12px",
  fontSize: "10px",
  fontWeight: "bold",
};

const routeCardStyle = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  padding: "10px 12px",
  fontSize: "12px",
};

const routeTypeStyle = {
  background: "rgba(255,255,255,0.1)",
  padding: "2px 6px",
  borderRadius: "4px",
  fontSize: "10px",
  color: "#aaa",
};

export default CommuteAdvisor;
