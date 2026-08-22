import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  FaTrafficLight,
  FaMapMarkedAlt,
  FaRoad,
  FaRobot,
  FaClock,
  FaChartLine,
  FaRoute,
  FaBell,
  FaHistory,
} from "react-icons/fa";

import AlertBanner from "./components/AlertBanner";
import CongestionGauge from "./components/CongestionGauge";
import TrafficMap from "./components/TrafficMap";
import HotspotHeatmap from "./components/HotspotHeatmap";
import ForecastPanel from "./components/ForecastPanel";
import HistoricalTrends from "./components/HistoricalTrends";
import CommuteAdvisor from "./components/CommuteAdvisor";

import {
  API_BASE_URL,
  LOCATIONS,
  STATUS_COLORS,
  WEATHER_OPTIONS,
} from "./config";

import "./App.css";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: <FaTrafficLight /> },
  { id: "map", label: "Live Map", icon: <FaMapMarkedAlt /> },
  { id: "forecast", label: "12h Forecast", icon: <FaChartLine /> },
  { id: "hotspots", label: "Hotspot Heatmap", icon: <FaBell /> },
  { id: "trends", label: "Historical Trends", icon: <FaHistory /> },
  { id: "commute", label: "Commute Advisor", icon: <FaRoute /> },
];

function App() {
  // ------------------------------------------------------------
  // Core state
  // ------------------------------------------------------------

  const [activeTab, setActiveTab] = useState("dashboard");
  const [location, setLocation] = useState("Marathahalli Bridge");
  const [weather, setWeather] = useState("Sunny");
  const [trafficVolume, setTrafficVolume] = useState("");
  const [averageSpeed, setAverageSpeed] = useState("");
  const [currentTime, setCurrentTime] = useState("");

  // ------------------------------------------------------------
  // Prediction state
  // ------------------------------------------------------------

  const [predResult, setPredResult] = useState(null);
  const [predLoading, setPredLoading] = useState(false);

  // ------------------------------------------------------------
  // Database state
  // ------------------------------------------------------------

  const [history, setHistory] = useState([]);
  const [dashboardData, setDashboardData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ------------------------------------------------------------
  // Remote data
  // ------------------------------------------------------------

  const [hotspots, setHotspots] = useState([]);
  const [hotspotMeta, setHotspotMeta] = useState({});
  const [incidents, setIncidents] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [trends, setTrends] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  const [liveTraffic, setLiveTraffic] = useState(null);
  const [liveTrafficLoading, setLiveTrafficLoading] = useState(false);

  const [memoryInsight, setMemoryInsight] = useState("");

  // ------------------------------------------------------------
  // Clock
  // ------------------------------------------------------------

  useEffect(() => {
    const updateClock = () => {
      setCurrentTime(
        new Date().toLocaleTimeString("en-IN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "Asia/Kolkata",
        })
      );
    };

    updateClock();

    const timer = setInterval(updateClock, 1000);

    return () => clearInterval(timer);
  }, []);

  // ------------------------------------------------------------
  // Fetch prediction history from SQLite
  // ------------------------------------------------------------

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);

    try {
      const response = await axios.get(`${API_BASE_URL}/history`);

      const records = response.data.predictions || [];

      const normalizedHistory = records.map((item) => ({
        id: item.id,
        location: item.location,
        prediction: Number(item.predicted_congestion || 0),
        weather: item.weather,
        trafficVolume: item.traffic_volume,
        averageSpeed: item.average_speed,
        time: item.timestamp,
        trafficStatus: item.traffic_status,
      }));

      setHistory(normalizedHistory);
    } catch (error) {
      console.error("Prediction history fetch failed:", error);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // ------------------------------------------------------------
  // Fetch dashboard analytics from SQLite
  // ------------------------------------------------------------

  const fetchDashboard = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/dashboard`);
      setDashboardData(response.data);
    } catch (error) {
      console.error("Dashboard fetch failed:", error);
    }
  }, []);

  // ------------------------------------------------------------
  // Initial database loading + automatic refresh
  // ------------------------------------------------------------

  useEffect(() => {
    fetchHistory();
    fetchDashboard();

    const interval = setInterval(() => {
      fetchHistory();
      fetchDashboard();
    }, 30000);

    return () => clearInterval(interval);
  }, [fetchHistory, fetchDashboard]);

  // ------------------------------------------------------------
  // Fetch hotspots
  // ------------------------------------------------------------

  const fetchHotspots = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/hotspots`, {
        params: { weather },
      });

      if (response.data.hotspots) {
        setHotspots(response.data.hotspots);

        setHotspotMeta({
          worst: response.data.worst_location,
          best: response.data.best_location,
          cityAvg: response.data.city_average_congestion,
        });
      }
    } catch (error) {
      console.error("Hotspots fetch failed:", error);
    }
  }, [weather]);

  useEffect(() => {
    fetchHotspots();

    const interval = setInterval(fetchHotspots, 60000);

    return () => clearInterval(interval);
  }, [fetchHotspots]);

  // ------------------------------------------------------------
  // Fetch incidents
  // ------------------------------------------------------------

  const fetchIncidents = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/incidents`);

      setIncidents(response.data.incidents || []);
    } catch (error) {
      console.error("Incident fetch failed:", error);
    }
  }, []);

  useEffect(() => {
    fetchIncidents();

    const interval = setInterval(fetchIncidents, 120000);

    return () => clearInterval(interval);
  }, [fetchIncidents]);

  // ------------------------------------------------------------
// Fetch live TomTom traffic
// ------------------------------------------------------------

  const fetchLiveTraffic = useCallback(async () => {
    setLiveTrafficLoading(true);

    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/live-traffic`,
        {
          params: {
            latitude: 12.9566,
            longitude: 77.7010,
          },
        }
      );

      setLiveTraffic(response.data);

      console.log("TomTom live traffic:", response.data);
    } catch (error) {
      console.error("Live TomTom traffic fetch failed:", error);
    } finally {
      setLiveTrafficLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLiveTraffic();

    const interval = setInterval(fetchLiveTraffic, 60000);

    return () => clearInterval(interval);
  }, [fetchLiveTraffic]);


  // ------------------------------------------------------------
  // Forecast
  // ------------------------------------------------------------

  useEffect(() => {
    axios
      .post(`${API_BASE_URL}/forecast`, {
        location,
        weather,
      })
      .then((response) => {
        setForecast(response.data);
      })
      .catch((error) => {
        console.error("Forecast fetch failed:", error);
      });
  }, [location, weather]);

  // ------------------------------------------------------------
  // Historical trends
  // ------------------------------------------------------------

  useEffect(() => {
    axios
      .get(`${API_BASE_URL}/historical-trends`, {
        params: { weather },
      })
      .then((response) => {
        setTrends(response.data);
      })
      .catch((error) => {
        console.error("Trends fetch failed:", error);
      });
  }, [weather]);

  // ------------------------------------------------------------
  // Analytics
  // ------------------------------------------------------------

  useEffect(() => {
    axios
      .get(`${API_BASE_URL}/analytics`, {
        params: {
          location,
          weather,
        },
      })
      .then((response) => {
        setAnalytics(response.data);
      })
      .catch((error) => {
        console.error("Analytics fetch failed:", error);
      });
  }, [location, weather]);

  // ------------------------------------------------------------
  // Memory insight
  // ------------------------------------------------------------

  const generateMemoryInsight = useCallback(
    (records) => {
      if (records.length < 3) {
        setMemoryInsight(
          "Learning Bengaluru traffic behavior..."
        );
        return;
      }

      const recent = records.slice(0, 3);

      const average =
        recent.reduce(
          (sum, item) => sum + Number(item.prediction || 0),
          0
        ) / recent.length;

      if (average > 20) {
        setMemoryInsight(
          `${location} shows repeated severe congestion. Mem-Brain recommends alternate route planning.`
        );
      } else if (average > 12) {
        setMemoryInsight(
          `${location} is experiencing recurring moderate congestion behavior.`
        );
      } else {
        setMemoryInsight(
          `${location} traffic flow appears stable based on memory analysis.`
        );
      }
    },
    [location]
  );

  // ------------------------------------------------------------
  // Prediction
  // ------------------------------------------------------------

  const predictTraffic = async () => {
    if (trafficVolume === "" || averageSpeed === "") {
      alert("Please enter Traffic Volume and Average Speed.");
      return;
    }

    const volume = Number(trafficVolume);
    const speed = Number(averageSpeed);

    if (volume < 0 || volume > 500) {
      alert("Traffic Volume must be between 0 and 500.");
      return;
    }

    if (speed < 0 || speed > 120) {
      alert("Average Speed must be between 0 and 120 km/h.");
      return;
    }

    setPredLoading(true);

    try {
      const response = await axios.post(
        `${API_BASE_URL}/predict`,
        {
          location,
          traffic_volume: parseInt(trafficVolume, 10),
          average_speed: parseFloat(averageSpeed),
          weather,
        }
      );

      const data = response.data;

      setPredResult(data);

      // The backend stores the prediction in SQLite.
      await fetchHistory();
      await fetchDashboard();

      generateMemoryInsight([
        ...history,
        {
          location,
          prediction: data.predicted_congestion,
          weather,
          trafficVolume,
          averageSpeed,
        },
      ]);
    } catch (error) {
      console.error("Prediction failed:", error);

      const message =
        error.response?.data?.detail ||
        "Prediction failed. Is the backend running?";

      alert(message);
    } finally {
      setPredLoading(false);
    }
  };

  // ------------------------------------------------------------
  // Prediction values
  // ------------------------------------------------------------

  const predValue =
    Number(predResult?.predicted_congestion) || 0;

  const predStatus =
    predResult?.traffic_status || null;

  const statusColor =
    predStatus && STATUS_COLORS[predStatus]
      ? STATUS_COLORS[predStatus]
      : "#888";

  const predictionCount =
    dashboardData?.analytics?.total_predictions ??
    history.length;

  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------

  return (
    <div className="app-root">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="app-header">

        <div className="header-brand">

          <span className="brand-icon">🚦</span>

          <div>
            <h1 className="brand-title">
              Bengaluru Pulse
            </h1>

            <p className="brand-sub">
              AI-Powered Urban Traffic Intelligence System
            </p>
          </div>

        </div>

        <div className="header-controls">

          <div className="weather-selector">

            {WEATHER_OPTIONS.map((item) => (
              <button
                key={item}
                className={`weather-btn ${
                  weather === item ? "active" : ""
                }`}
                onClick={() => setWeather(item)}
              >
                {item === "Sunny"
                  ? "☀️"
                  : item === "Cloudy"
                  ? "☁️"
                  : "🌧️"}{" "}
                {item}
              </button>
            ))}

          </div>

          <div className="clock-badge">
            <FaClock className="clock-icon" />
            <span className="clock-time">
              {currentTime}
            </span>
          </div>

        </div>

      </header>

      {/* ======================================================
          ALERTS
      ====================================================== */}

      <div className="alert-zone">
        <AlertBanner
          hotspots={hotspots}
          incidents={incidents}
        />
      </div>

      {/* ======================================================
          KPI CARDS
      ====================================================== */}

      <div className="kpi-grid">

        {[
          {
            label: "City Avg Congestion",
            value:
              hotspotMeta.cityAvg !== undefined
                ? Number(hotspotMeta.cityAvg).toFixed(1)
                : "--",
            icon: "📊",
            color: "#00bfff",
          },
          {
            label: "Worst Hotspot",
            value: hotspotMeta.worst || "--",
            icon: "🔴",
            color: "#ff3333",
          },
          {
            label: "Best Location",
            value: hotspotMeta.best || "--",
            icon: "🟢",
            color: "#00ff99",
          },
          {
            label: "Predictions Made",
            value: predictionCount,
            icon: "🧠",
            color: "#bb66ff",
          },
          {
            label: "Weather",
            value: weather,
            icon:
              weather === "Sunny"
                ? "☀️"
                : weather === "Cloudy"
                ? "☁️"
                : "🌧️",
            color: "#ffcc00",
          },
          {
            label: "Active Alerts",
            value:
              hotspots.filter(
                (item) =>
                  item.status === "SEVERE" ||
                  item.status === "HIGH"
              ).length + incidents.length,
            icon: "⚠️",
            color: "#ff8800",
          },
        ].map((kpi, index) => (
          <motion.div
            key={kpi.label}
            className="kpi-card"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06 }}
            style={{ "--accent": kpi.color }}
          >
            <div className="kpi-icon">{kpi.icon}</div>

            <div
              className="kpi-value"
              style={{ color: kpi.color }}
            >
              {kpi.value}
            </div>

            <div className="kpi-label">
              {kpi.label}
            </div>
          </motion.div>
        ))}

      </div>

      {/* ======================================================
          NAVIGATION
      ====================================================== */}

      <nav className="tab-nav">

        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${
              activeTab === tab.id ? "active" : ""
            }`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-icon">
              {tab.icon}
            </span>

            <span className="tab-label">
              {tab.label}
            </span>
          </button>
        ))}

      </nav>

      {/* ======================================================
          CONTENT
      ====================================================== */}

      <AnimatePresence mode="wait">

        <motion.div
          key={activeTab}
          className="tab-content"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.25 }}
        >

          {/* ==================================================
              DASHBOARD
          ================================================== */}

          {activeTab === "dashboard" && (
            <div className="dashboard-grid">

              {/* Prediction */}

              <div className="glass-card predict-card">

                <h2 className="card-title">
                  <FaTrafficLight />
                  Traffic Prediction
                </h2>

                <label className="field-label">
                  Location
                </label>

                <select
                  className="field-input"
                  value={location}
                  onChange={(event) =>
                    setLocation(event.target.value)
                  }
                >
                  {LOCATIONS.map((item) => (
                    <option key={item}>
                      {item}
                    </option>
                  ))}
                </select>

                <label className="field-label">
                  Traffic Volume{" "}
                  <span className="field-hint">
                    (0 – 500)
                  </span>
                </label>

                <input
                  className="field-input"
                  type="number"
                  placeholder="e.g. 150"
                  value={trafficVolume}
                  onChange={(event) =>
                    setTrafficVolume(event.target.value)
                  }
                />

                <label className="field-label">
                  Average Speed{" "}
                  <span className="field-hint">
                    (km/h)
                  </span>
                </label>

                <input
                  className="field-input"
                  type="number"
                  placeholder="e.g. 35"
                  value={averageSpeed}
                  onChange={(event) =>
                    setAverageSpeed(event.target.value)
                  }
                />

                <button
                  className="predict-btn"
                  onClick={predictTraffic}
                  disabled={predLoading}
                >
                  {predLoading ? (
                    <span className="spinner" />
                  ) : (
                    "⚡ Predict Traffic"
                  )}
                </button>

                {predResult && (
                  <motion.div
                    className="pred-result-box"
                    initial={{
                      scale: 0.9,
                      opacity: 0,
                    }}
                    animate={{
                      scale: 1,
                      opacity: 1,
                    }}
                    style={{
                      "--status-color": statusColor,
                    }}
                  >

                    <div className="pred-result-label">
                      Congestion Index
                    </div>

                    <div
                      className="pred-result-value"
                      style={{
                        color: statusColor,
                      }}
                    >
                      {predValue.toFixed(1)}
                    </div>

                    <div
                      className="pred-result-status"
                      style={{
                        color: statusColor,
                      }}
                    >
                      {predResult.signal === "GREEN"
                        ? "🟢"
                        : predResult.signal === "YELLOW"
                        ? "🟡"
                        : "🔴"}{" "}
                      {predStatus}
                    </div>

                    <div className="pred-delay">
                      ⏱ Est. delay:{" "}
                      {predResult.estimated_delay_minutes}{" "}
                      min
                    </div>

                  </motion.div>
                )}

              </div>

              {/* Gauge */}

              <div className="glass-card gauge-card">

                <h2 className="card-title">
                  Congestion Meter
                </h2>

                <div className="gauge-center">
                  <CongestionGauge
                    value={predValue}
                    size={230}
                  />
                </div>

                {predResult && (
                  <div className="gauge-reco">

                    <FaRobot
                      style={{
                        color: "#00bfff",
                        marginRight: "6px",
                      }}
                    />

                    {predResult.recommendation}

                  </div>
                )}

              </div>

              {/* Explainable AI */}

              <div className="glass-card xai-card">

                <h2 className="card-title">
                  <FaRobot />
                  Explainable AI
                </h2>

                <div className="xai-grid">

                  {[
                    {
                      key: "Location",
                      val: location,
                    },
                    {
                      key: "Weather",
                      val: weather,
                    },
                    {
                      key: "Traffic Volume",
                      val: trafficVolume || "--",
                    },
                    {
                      key: "Avg Speed",
                      val: averageSpeed
                        ? `${averageSpeed} km/h`
                        : "--",
                    },
                    {
                      key: "Density",
                      val: predResult
                        ? `${Math.min(
                            predValue * 4,
                            100
                          ).toFixed(0)}%`
                        : "--",
                    },
                    {
                      key: "Status",
                      val: predStatus || "--",
                      color: statusColor,
                    },
                  ].map((item) => (
                    <div
                      className="xai-row"
                      key={item.key}
                    >
                      <span className="xai-key">
                        {item.key}
                      </span>

                      <span
                        className="xai-val"
                        style={{
                          color:
                            item.color || "#fff",
                        }}
                      >
                        {item.val}
                      </span>
                    </div>
                  ))}

                </div>

                <div className="mem-brain-box">

                  <div className="mem-brain-title">
                    🧠 Mem-Brain Engine
                  </div>

                  <p className="mem-brain-text">
                    {memoryInsight ||
                      "Traffic memory engine initializing..."}
                  </p>

                  <div className="mem-brain-count">
                    {historyLoading
                      ? "Loading stored records..."
                      : `Stored records: ${predictionCount}`}
                  </div>

                </div>

              </div>

              {/* Analytics */}

              {analytics && (
                <div className="glass-card analytics-card">

                  <h2 className="card-title">
                    <FaChartLine />
                    Today's Analytics
                  </h2>

                  <div className="analytics-stats">

                    <div className="stat-block">
                      <div
                        className="stat-val"
                        style={{ color: "#00bfff" }}
                      >
                        {analytics.daily_avg_congestion}
                      </div>
                      <div className="stat-lbl">
                        Daily Average
                      </div>
                    </div>

                    <div className="stat-block">
                      <div
                        className="stat-val"
                        style={{ color: "#ff8800" }}
                      >
                        {analytics.risk_score}
                      </div>
                      <div className="stat-lbl">
                        Risk Score
                      </div>
                    </div>

                    <div className="stat-block">
                      <div
                        className="stat-val"
                        style={{ color: "#ff3333" }}
                      >
                        {analytics.congestion_distribution
                          ?.SEVERE ?? 0}
                        h
                      </div>
                      <div className="stat-lbl">
                        Severe Hours
                      </div>
                    </div>

                    <div className="stat-block">
                      <div
                        className="stat-val"
                        style={{ color: "#00ff99" }}
                      >
                        {analytics.congestion_distribution
                          ?.LOW ?? 0}
                        h
                      </div>
                      <div className="stat-lbl">
                        Clear Hours
                      </div>
                    </div>

                  </div>

                  <div className="analytics-peaks">

                    <div
                      style={{
                        fontSize: "12px",
                        color: "#aaa",
                        marginBottom: "6px",
                      }}
                    >
                      Top Peak Hours
                    </div>

                    {analytics.top_peak_hours?.map(
                      (peak) => (
                        <div
                          key={peak.hour}
                          className="peak-row"
                        >
                          <span
                            style={{
                              color: "#ddd",
                            }}
                          >
                            {peak.label}
                          </span>

                          <span
                            style={{
                              color:
                                STATUS_COLORS[
                                  peak.status
                                ],
                            }}
                          >
                            {Number(
                              peak.congestion
                            ).toFixed(1)}{" "}
                            — {peak.status}
                          </span>
                        </div>
                      )
                    )}

                  </div>

                </div>
              )}

              {/* ==================================================
                  DATABASE HISTORY
              ================================================== */}

              <div className="glass-card analytics-card">

                <h2 className="card-title">
                  <FaHistory />
                  Prediction History
                </h2>

                {historyLoading ? (
                  <div
                    style={{
                      color: "#aaa",
                      padding: "20px 0",
                    }}
                  >
                    Loading prediction history...
                  </div>
                ) : history.length === 0 ? (
                  <div
                    style={{
                      color: "#aaa",
                      padding: "20px 0",
                    }}
                  >
                    No predictions stored yet.
                  </div>
                ) : (
                  <div
                    style={{
                      overflowX: "auto",
                    }}
                  >

                    <table
                      style={{
                        width: "100%",
                        borderCollapse:
                          "collapse",
                      }}
                    >

                      <thead>

                        <tr
                          style={{
                            color: "#aaa",
                            textAlign: "left",
                          }}
                        >
                          <th style={{ padding: "10px" }}>
                            Location
                          </th>

                          <th style={{ padding: "10px" }}>
                            Congestion
                          </th>

                          <th style={{ padding: "10px" }}>
                            Status
                          </th>

                          <th style={{ padding: "10px" }}>
                            Weather
                          </th>

                          <th style={{ padding: "10px" }}>
                            Volume
                          </th>

                          <th style={{ padding: "10px" }}>
                            Speed
                          </th>

                          <th style={{ padding: "10px" }}>
                            Time
                          </th>
                        </tr>

                      </thead>

                      <tbody>

                        {history
                          .slice(0, 10)
                          .map((item, index) => {

                            const color =
                              STATUS_COLORS[
                                item.trafficStatus
                              ] || "#00bfff";

                            return (
                              <tr
                                key={
                                  item.id ||
                                  `${item.location}-${item.time}-${index}`
                                }
                              >

                                <td
                                  style={{
                                    padding: "10px",
                                    color: "#ddd",
                                  }}
                                >
                                  {item.location}
                                </td>

                                <td
                                  style={{
                                    padding: "10px",
                                    color,
                                  }}
                                >
                                  {Number(
                                    item.prediction
                                  ).toFixed(2)}
                                </td>

                                <td
                                  style={{
                                    padding: "10px",
                                    color,
                                  }}
                                >
                                  {item.trafficStatus ||
                                    "--"}
                                </td>

                                <td
                                  style={{
                                    padding: "10px",
                                    color: "#ddd",
                                  }}
                                >
                                  {item.weather || "--"}
                                </td>

                                <td
                                  style={{
                                    padding: "10px",
                                    color: "#ddd",
                                  }}
                                >
                                  {item.trafficVolume ??
                                    "--"}
                                </td>

                                <td
                                  style={{
                                    padding: "10px",
                                    color: "#ddd",
                                  }}
                                >
                                  {item.averageSpeed ??
                                    "--"}{" "}
                                  km/h
                                </td>

                                <td
                                  style={{
                                    padding: "10px",
                                    color: "#aaa",
                                  }}
                                >
                                  {item.time || "--"}
                                </td>

                              </tr>
                            );
                          })}

                      </tbody>

                    </table>

                  </div>
                )}

              </div>

            </div>
          )}

          {/* ==================================================
              LIVE MAP
          ================================================== */}

          {activeTab === "map" && (
            <div className="map-layout">

              <div className="glass-card map-main-card">

                <h2 className="card-title">
                  <FaMapMarkedAlt />
                  Live Traffic Map — Bengaluru
                </h2>

                <div className="map-wrapper">

                  <TrafficMap
                    hotspots={hotspots}
                    selectedLocation={location}
                    onLocationSelect={setLocation}
                    liveTraffic={liveTraffic}
                    liveTrafficLoading={liveTrafficLoading}
                  />

                </div>

              </div>

              <div className="glass-card map-sidebar">

                <h2 className="card-title">
                  Location Details
                </h2>

                <div className="location-list">

                  {LOCATIONS.map((loc) => {

                    const spot = hotspots.find(
                      (item) =>
                        item.location === loc
                    );

                    const color = spot
                      ? STATUS_COLORS[
                          spot.status
                        ] || "#888"
                      : "#888";

                    return (
                      <button
                        key={loc}
                        className={`location-row ${
                          location === loc
                            ? "selected"
                            : ""
                        }`}
                        onClick={() =>
                          setLocation(loc)
                        }
                        style={{
                          "--accent": color,
                        }}
                      >

                        <div
                          className="loc-dot"
                          style={{
                            background: color,
                            boxShadow:
                              `0 0 6px ${color}`,
                          }}
                        />

                        <div className="loc-info">

                          <div className="loc-name">
                            {loc}
                          </div>

                          <div
                            className="loc-val"
                            style={{
                              color,
                            }}
                          >
                            {spot
                              ? `${Number(
                                  spot.congestion
                                ).toFixed(
                                  1
                                )} — ${
                                  spot.status
                                }`
                              : "Loading..."}
                          </div>

                        </div>

                        {spot?.is_peak_hour && (
                          <span className="peak-badge">
                            ⚡ Peak
                          </span>
                        )}

                      </button>
                    );
                  })}

                </div>

              </div>

            </div>
          )}

          {/* ==================================================
              FORECAST
          ================================================== */}

          {activeTab === "forecast" && (
            <div className="full-card-layout">

              <div
                className="glass-card"
                style={{ padding: "28px" }}
              >

                <div className="forecast-location-row">

                  <h2
                    className="card-title"
                    style={{ marginBottom: 0 }}
                  >
                    <FaChartLine />
                    12-Hour Forecast
                  </h2>

                  <select
                    className="field-input compact-select"
                    value={location}
                    onChange={(event) =>
                      setLocation(event.target.value)
                    }
                  >
                    {LOCATIONS.map((item) => (
                      <option key={item}>
                        {item}
                      </option>
                    ))}
                  </select>

                </div>

                <ForecastPanel
                  forecast={forecast?.forecast}
                  location={forecast?.location}
                  peakCongestion={
                    forecast?.peak_congestion
                  }
                  bestWindow={
                    forecast?.best_travel_window
                  }
                />

                {forecast?.summary && (
                  <div className="forecast-summary">
                    💡 {forecast.summary}
                  </div>
                )}

              </div>

            </div>
          )}

          {/* ==================================================
              HOTSPOTS
          ================================================== */}

          {activeTab === "hotspots" && (
            <div className="full-card-layout">

              <div
                className="glass-card"
                style={{ padding: "28px" }}
              >

                <h2 className="card-title">
                  <FaBell />
                  Congestion Hotspot Heatmap
                </h2>

                <HotspotHeatmap
                  hotspots={hotspots}
                  cityAverage={hotspotMeta.cityAvg}
                />

              </div>

            </div>
          )}

          {/* ==================================================
              HISTORICAL TRENDS
          ================================================== */}

          {activeTab === "trends" && (
            <div className="full-card-layout">

              <div
                className="glass-card"
                style={{ padding: "28px" }}
              >

                <h2 className="card-title">
                  <FaHistory />
                  Historical Trends
                </h2>

                <HistoricalTrends
                  trendData={trends?.trend_data}
                  locations={trends?.locations}
                  cityTrend={trends?.city_trend}
                />

                {trends && (
                  <div className="trends-footer">

                    <span>
                      Most congested today:{" "}
                      <strong
                        style={{
                          color: "#ff3333",
                        }}
                      >
                        {trends.most_congested_today}
                      </strong>
                    </span>

                    <span>
                      Least congested today:{" "}
                      <strong
                        style={{
                          color: "#00ff99",
                        }}
                      >
                        {trends.least_congested_today}
                      </strong>
                    </span>

                  </div>
                )}

              </div>

            </div>
          )}

          {/* ==================================================
              COMMUTE ADVISOR
          ================================================== */}

          {activeTab === "commute" && (
            <div className="commute-layout">

              <div
                className="glass-card commute-card"
                style={{ padding: "28px" }}
              >
                <CommuteAdvisor
                  locations={LOCATIONS}
                />
              </div>

              <div className="glass-card commute-tips">

                <h2 className="card-title">
                  🏙️ Smart City Tips
                </h2>

                {[
                  {
                    icon: "🚇",
                    tip: "Namma Metro Purple & Green Lines cover major IT corridors",
                  },
                  {
                    icon: "🕗",
                    tip: "Avoid Silk Board between 8–10 AM and 5–8 PM",
                  },
                  {
                    icon: "🌧️",
                    tip: "Rainy days add 30–50% to typical congestion times",
                  },
                  {
                    icon: "🏢",
                    tip: "Work-from-home on Fridays can reduce ORR congestion",
                  },
                  {
                    icon: "🚌",
                    tip: "BMTC Vajra buses offer AC travel on key corridors",
                  },
                  {
                    icon: "🛵",
                    tip: "Two-wheelers can use Hosur Road service lanes during peak hours",
                  },
                ].map((item, index) => (
                  <motion.div
                    key={index}
                    className="tip-row"
                    initial={{
                      opacity: 0,
                      x: -10,
                    }}
                    animate={{
                      opacity: 1,
                      x: 0,
                    }}
                    transition={{
                      delay: index * 0.08,
                    }}
                  >
                    <span className="tip-icon">
                      {item.icon}
                    </span>

                    <span className="tip-text">
                      {item.tip}
                    </span>
                  </motion.div>
                ))}

              </div>

            </div>
          )}

        </motion.div>

      </AnimatePresence>

      {/* ======================================================
          FOOTER
      ====================================================== */}

      <footer className="app-footer">
        <FaRoad /> Bengaluru Pulse
        &nbsp;•&nbsp; AI Urban Traffic Intelligence System
        &nbsp;•&nbsp; Mem-Brain Engine Active
      </footer>

    </div>
  );
}

export default App;