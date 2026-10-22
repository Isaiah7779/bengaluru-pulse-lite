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
import RoutePlanner from "./components/RoutePlanner";
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
  {
    id: "dashboard",
    label: "Dashboard",
    icon: <FaTrafficLight />,
  },
  {
    id: "map",
    label: "Live Map",
    icon: <FaMapMarkedAlt />,
  },
  {
    id: "forecast",
    label: "12h Forecast",
    icon: <FaChartLine />,
  },
  {
    id: "hotspots",
    label: "Hotspot Heatmap",
    icon: <FaBell />,
  },
  {
    id: "trends",
    label: "Historical Trends",
    icon: <FaHistory />,
  },
  {
    id: "commute",
    label: "Commute Advisor",
    icon: <FaRoute />,
  },
];

function App() {
  // ============================================================
  // CORE STATE
  // ============================================================

  const [activeTab, setActiveTab] = useState("dashboard");
  const [location, setLocation] = useState(
    "Marathahalli Bridge"
  );
  const [weather, setWeather] = useState("Sunny");
  const [trafficVolume, setTrafficVolume] = useState("");
  const [averageSpeed, setAverageSpeed] = useState("");
  const [currentTime, setCurrentTime] = useState("");

  // ============================================================
  // PREDICTION STATE
  // ============================================================

  const [predResult, setPredResult] = useState(null);
  const [predLoading, setPredLoading] = useState(false);

  // ============================================================
  // DATABASE STATE
  // ============================================================

  const [history, setHistory] = useState([]);
  const [dashboardData, setDashboardData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ============================================================
  // REMOTE DATA
  // ============================================================

  const [hotspots, setHotspots] = useState([]);
  const [hotspotMeta, setHotspotMeta] = useState({});
  const [incidents, setIncidents] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [trends, setTrends] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  // ============================================================
  // LIVE TRAFFIC
  // ============================================================

  const [liveTraffic, setLiveTraffic] = useState(null);
  const [liveTrafficLoading, setLiveTrafficLoading] =
    useState(false);

  // ============================================================
  // ROUTING STATE
  // ============================================================

  const [originText, setOriginText] =
    useState("Whitefield");

  const [destinationText, setDestinationText] =
    useState("Marathahalli");

  const [vehicle, setVehicle] = useState("car");

  const [routeResult, setRouteResult] = useState(null);
  const [routeLoading, setRouteLoading] = useState(false);

  // ============================================================
  // MEM-BRAIN
  // ============================================================

  const [memoryInsight, setMemoryInsight] = useState("");

  // ============================================================
  // CLOCK
  // ============================================================

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

    const timer = setInterval(
      updateClock,
      1000
    );

    return () => clearInterval(timer);
  }, []);

  // ============================================================
  // FETCH PREDICTION HISTORY
  // ============================================================

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);

    try {
      const response = await axios.get(
        `${API_BASE_URL}/history`
      );

      const records =
        response.data.predictions || [];

      const normalizedHistory =
        records.map((item) => ({
          id: item.id,
          location: item.location,
          prediction: Number(
            item.predicted_congestion || 0
          ),
          weather: item.weather,
          trafficVolume:
            item.traffic_volume,
          averageSpeed:
            item.average_speed,
          time: item.timestamp,
          trafficStatus:
            item.traffic_status,
        }));

      setHistory(normalizedHistory);
    } catch (error) {
      console.error(
        "Prediction history fetch failed:",
        error
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // ============================================================
  // FETCH DASHBOARD
  // ============================================================

  const fetchDashboard = useCallback(
    async () => {
      try {
        const response = await axios.get(
          `${API_BASE_URL}/dashboard`
        );

        setDashboardData(response.data);
      } catch (error) {
        console.error(
          "Dashboard fetch failed:",
          error
        );
      }
    },
    []
  );

  // ============================================================
  // INITIAL DATABASE LOADING + REFRESH
  // ============================================================

  useEffect(() => {
    fetchHistory();
    fetchDashboard();

    const interval = setInterval(() => {
      fetchHistory();
      fetchDashboard();
    }, 30000);

    return () => clearInterval(interval);
  }, [
    fetchHistory,
    fetchDashboard,
  ]);

  // ============================================================
  // FETCH HOTSPOTS
  // ============================================================

  const fetchHotspots = useCallback(
    async () => {
      try {
        const response = await axios.get(
          `${API_BASE_URL}/hotspots`,
          {
            params: { weather },
          }
        );

        if (response.data.hotspots) {
          setHotspots(
            response.data.hotspots
          );

          setHotspotMeta({
            worst:
              response.data.worst_location,
            best:
              response.data.best_location,
            cityAvg:
              response.data
                .city_average_congestion,
          });
        }
      } catch (error) {
        console.error(
          "Hotspots fetch failed:",
          error
        );
      }
    },
    [weather]
  );

  useEffect(() => {
    fetchHotspots();

    const interval = setInterval(
      fetchHotspots,
      60000
    );

    return () => clearInterval(interval);
  }, [fetchHotspots]);

  // ============================================================
  // FETCH INCIDENTS
  // ============================================================

  const fetchIncidents = useCallback(
    async () => {
      try {
        const response = await axios.get(
          `${API_BASE_URL}/incidents`
        );

        setIncidents(
          response.data.incidents || []
        );
      } catch (error) {
        console.error(
          "Incident fetch failed:",
          error
        );
      }
    },
    []
  );

  useEffect(() => {
    fetchIncidents();

    const interval = setInterval(
      fetchIncidents,
      120000
    );

    return () => clearInterval(interval);
  }, [fetchIncidents]);

  // ============================================================
  // FETCH LIVE TOMTOM TRAFFIC
  // ============================================================

  const fetchLiveTraffic =
    useCallback(async () => {
      setLiveTrafficLoading(true);

      try {
        const response = await axios.get(
          `${API_BASE_URL}/api/live-traffic/bengaluru`
        );

        setLiveTraffic(
          response.data
        );

        console.log(
          "TomTom live traffic:",
          response.data
        );
      } catch (error) {
        console.error(
          "Live TomTom traffic fetch failed:",
          error
        );
      } finally {
        setLiveTrafficLoading(false);
      }
    }, []);

  useEffect(() => {
    fetchLiveTraffic();

    const interval = setInterval(
      fetchLiveTraffic,
      60000
    );

    return () => clearInterval(interval);
  }, [fetchLiveTraffic]);

  // ============================================================
  // FORECAST
  // ============================================================

  useEffect(() => {
    axios
      .post(
        `${API_BASE_URL}/forecast`,
        {
          location,
          weather,
        }
      )
      .then((response) => {
        setForecast(response.data);
      })
      .catch((error) => {
        console.error(
          "Forecast fetch failed:",
          error
        );
      });
  }, [location, weather]);

  // ============================================================
  // HISTORICAL TRENDS
  // ============================================================

  useEffect(() => {
    axios
      .get(
        `${API_BASE_URL}/historical-trends`,
        {
          params: { weather },
        }
      )
      .then((response) => {
        setTrends(response.data);
      })
      .catch((error) => {
        console.error(
          "Trends fetch failed:",
          error
        );
      });
  }, [weather]);

  // ============================================================
  // ANALYTICS
  // ============================================================

  useEffect(() => {
    axios
      .get(
        `${API_BASE_URL}/analytics`,
        {
          params: {
            location,
            weather,
          },
        }
      )
      .then((response) => {
        setAnalytics(response.data);
      })
      .catch((error) => {
        console.error(
          "Analytics fetch failed:",
          error
        );
      });
  }, [location, weather]);

  // ============================================================
  // MEM-BRAIN INSIGHT
  // ============================================================

  const generateMemoryInsight =
    useCallback(
      (records) => {
        if (records.length < 3) {
          setMemoryInsight(
            "Learning Bengaluru traffic behavior..."
          );
          return;
        }

        const recent =
          records.slice(0, 3);

        const average =
          recent.reduce(
            (sum, item) =>
              sum +
              Number(
                item.prediction || 0
              ),
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


    const geocodeBengaluru = async (query) => {
  const response = await axios.get(
    "https://photon.komoot.io/api/",
    {
      params: {
        q: `${query}, Bengaluru, Karnataka, India`,
        limit: 1,
      },
      timeout: 10000,
    }
  );

  const feature = response.data?.features?.[0];

  if (!feature?.geometry?.coordinates) {
    throw new Error(
      `Could not find "${query}" in Bengaluru.`
    );
  }

  const [lon, lat] = feature.geometry.coordinates;

  return {
    lat: Number(lat),
    lon: Number(lon),
  };
};
  // ============================================================
  // OSRM ROUTE CALCULATION
  // ============================================================

   // ============================================================
  // BENGALURU PULSE ROUTE CALCULATION
  // OSRM + TOMTOM LIVE TRAFFIC
  // ============================================================

  const calculateRoute = async () => {
    // ------------------------------------------------------------
    // 1. Validate input
    // ------------------------------------------------------------

    if (
      !originText ||
      !originText.trim() ||
      !destinationText ||
      !destinationText.trim()
    ) {
      alert("Please enter both origin and destination.");
      return;
    }

    // ------------------------------------------------------------
    // 2. Start loading state
    // ------------------------------------------------------------

    setRouteLoading(true);

    // Clear previous route while calculating
    setRouteResult(null);

    try {
      // ----------------------------------------------------------
      // 3. Temporary Bengaluru geocoding dictionary
      //
      // IMPORTANT:
      // This is currently used because the frontend does not yet
      // have a real geocoding/search service.
      //
      // Later we can replace this with Nominatim/Photon/etc.
      // ----------------------------------------------------------

      
      // ----------------------------------------------------------
      // 4. Normalize user input
      // ----------------------------------------------------------

      // ----------------------------------------------------------
      // 5. Resolve coordinates
      // ----------------------------------------------------------

      const origin = await geocodeBengaluru(originText);
      const destination = await geocodeBengaluru(destinationText);

      // ----------------------------------------------------------
      // 6. Validate origin
      // ----------------------------------------------------------

      if (!origin) {
        alert(
          `Location "${originText}" is not available yet.\n\n` +
          `Try one of:\n` +
          `Whitefield\n` +
          `Marathahalli\n` +
          `Kundalahalli\n` +
          `Brookefield\n` +
          `KR Puram\n` +
          `Hebbal\n` +
          `Silk Board\n` +
          `Electronic City\n` +
          `Indiranagar\n` +
          `Koramangala\n` +
          `Jayanagar\n` +
          `MG Road`
        );

        return;
      }

      // ----------------------------------------------------------
      // 7. Validate destination
      // ----------------------------------------------------------

      if (!destination) {
        alert(
          `Location "${destinationText}" is not available yet.\n\n` +
          `Try one of:\n` +
          `Whitefield\n` +
          `Marathahalli\n` +
          `Kundalahalli\n` +
          `Brookefield\n` +
          `KR Puram\n` +
          `Hebbal\n` +
          `Silk Board\n` +
          `Electronic City\n` +
          `Indiranagar\n` +
          `Koramangala\n` +
          `Jayanagar\n` +
          `MG Road`
        );

        return;
      }

      // ----------------------------------------------------------
      // 8. Prevent same-location routing
      // ----------------------------------------------------------

      const sameLocation =
        Math.abs(origin.lat - destination.lat) < 0.00001 &&
        Math.abs(origin.lon - destination.lon) < 0.00001;

      if (sameLocation) {
        alert(
          "Origin and destination cannot be the same location."
        );

        return;
      }

      // ----------------------------------------------------------
      // 9. Build routing request
      // ----------------------------------------------------------

      const requestPayload = {
        origin: {
          lat: Number(origin.lat),
          lon: Number(origin.lon),
        },

        destination: {
          lat: Number(destination.lat),
          lon: Number(destination.lon),
        },

        // Supported frontend vehicle values:
        // car
        // motorcycle
        // bicycle
        // walk

        vehicle: vehicle || "car",

        // Ask backend for alternatives
        alternatives: true,

        // Request complete geometry
        overview: true,

        // Request turn-by-turn steps
        steps: true,
      };

      // ----------------------------------------------------------
      // 10. Debug request
      // ----------------------------------------------------------

      console.log(
        "================================================"
      );

      console.log(
        "BENGALURU PULSE ROUTING REQUEST"
      );

      console.log(
        "================================================"
      );

      console.log(
        "Origin:",
        originText,
        origin
      );

      console.log(
        "Destination:",
        destinationText,
        destination
      );

      console.log(
        "Vehicle:",
        vehicle
      );

      console.log(
        "Payload:",
        requestPayload
      );

      // ----------------------------------------------------------
      // 11. Call FastAPI routing backend
      // ----------------------------------------------------------

      const response = await axios.post(
        `${API_BASE_URL}/routing/route`,
        requestPayload,
        {
          timeout: 30000,

          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      // ----------------------------------------------------------
      // 12. Validate backend response
      // ----------------------------------------------------------

      if (!response || !response.data) {
        throw new Error(
          "Routing backend returned an empty response."
        );
      }

      const routeData = response.data;

      // ----------------------------------------------------------
      // 13. Validate routes
      // ----------------------------------------------------------

      if (
        !routeData.routes ||
        !Array.isArray(routeData.routes) ||
        routeData.routes.length === 0
      ) {
        throw new Error(
          "No route was found between the selected locations."
        );
      }

      // ----------------------------------------------------------
      // 14. Normalize route data for frontend
      //
      // This keeps the UI compatible even if some optional
      // intelligence fields are missing from the backend.
      // ----------------------------------------------------------

      const normalizedRoutes =
        routeData.routes.map(
          (route, index) => {
            const distanceKm =
              Number(
                route.distance_km
              ) ||
              Number(
                route.distance_m
              ) / 1000 ||
              0;

            const durationMin =
              Number(
                route.duration_min
              ) ||
              Number(
                route.duration_s
              ) / 60 ||
              0;

            const liveEtaMin =
              route.live_eta_min !== null &&
              route.live_eta_min !== undefined
                ? Number(
                    route.live_eta_min
                  )
                : durationMin;

            const baseEtaMin =
              route.base_eta_min !== null &&
              route.base_eta_min !== undefined
                ? Number(
                    route.base_eta_min
                  )
                : durationMin;

            const trafficDelayMin =
              route.traffic_delay_min !== null &&
              route.traffic_delay_min !== undefined
                ? Number(
                    route.traffic_delay_min
                  )
                : Math.max(
                    liveEtaMin -
                      baseEtaMin,
                    0
                  );

            const trafficRatio =
              route.traffic_ratio !== null &&
              route.traffic_ratio !== undefined
                ? Number(
                    route.traffic_ratio
                  )
                : 1;

            const routeScore =
              route.route_score !== null &&
              route.route_score !== undefined
                ? Number(
                    route.route_score
                  )
                : liveEtaMin;

            return {
              ...route,

              // Ensure frontend has stable values
              route_id:
                route.route_id ||
                `route-${index + 1}`,

              distance_m:
                Number(
                  route.distance_m
                ) ||
                distanceKm * 1000,

              duration_s:
                Number(
                  route.duration_s
                ) ||
                durationMin * 60,

              distance_km:
                Number(
                  distanceKm.toFixed(3)
                ),

              duration_min:
                Number(
                  durationMin.toFixed(2)
                ),

              live_eta_min:
                Number(
                  liveEtaMin.toFixed(2)
                ),

              base_eta_min:
                Number(
                  baseEtaMin.toFixed(2)
                ),

              traffic_delay_min:
                Number(
                  Math.max(
                    trafficDelayMin,
                    0
                  ).toFixed(2)
                ),

              traffic_ratio:
                Number(
                  trafficRatio.toFixed(3)
                ),

              route_score:
                Number(
                  routeScore.toFixed(3)
                ),

              traffic_status:
                route.traffic_status ||
                "UNKNOWN",

              traffic_source:
                route.traffic_source ||
                "OSRM",

              intelligence_available:
                route.intelligence_available !==
                  undefined
                  ? route.intelligence_available
                  : false,

              recommended:
                route.recommended === true,
            };
          }
        );

      // ----------------------------------------------------------
      // 15. Sort routes
      //
      // Backend normally performs this already.
      // We keep frontend ordering stable using route_score.
      // ----------------------------------------------------------

      normalizedRoutes.sort(
        (a, b) => {
          return (
            Number(a.route_score || 0) -
            Number(b.route_score || 0)
          );
        }
      );

      // ----------------------------------------------------------
      // 16. Mark recommended route
      //
      // Only do this if backend did not already mark one.
      // ----------------------------------------------------------

      const backendRecommended =
        normalizedRoutes.some(
          (route) =>
            route.recommended === true
        );

      const finalRoutes =
        normalizedRoutes.map(
          (route, index) => ({
            ...route,

            recommended:
              backendRecommended
                ? route.recommended === true
                : index === 0,
          })
        );

      // ----------------------------------------------------------
      // 17. Create final response object
      // ----------------------------------------------------------

      const finalRouteResult = {
        ...routeData,

        source:
          routeData.source ||
          "osrm",

        vehicle:
          routeData.vehicle ||
          vehicle,

        routes: finalRoutes,

        // Frontend metadata
        origin: {
          ...origin,
          name: originText,
        },

        destination: {
          ...destination,
          name: destinationText,
        },

        calculated_at:
          new Date().toISOString(),
      };

      // ----------------------------------------------------------
      // 18. Log final routing result
      // ----------------------------------------------------------

      console.log(
        "================================================"
      );

      console.log(
        "BENGALURU PULSE ROUTING RESULT"
      );

      console.log(
        "================================================"
      );

      console.log(
        "Source:",
        finalRouteResult.source
      );

      console.log(
        "Vehicle:",
        finalRouteResult.vehicle
      );

      console.log(
        "Number of routes:",
        finalRoutes.length
      );

      console.table(
        finalRoutes.map(
          (route, index) => ({
            Route:
              index + 1,

            Recommended:
              route.recommended
                ? "YES"
                : "NO",

            Distance:
              `${route.distance_km} km`,

            BaseETA:
              `${route.base_eta_min} min`,

            LiveETA:
              `${route.live_eta_min} min`,

            TrafficDelay:
              `${route.traffic_delay_min} min`,

            Traffic:
              route.traffic_status,

            Score:
              route.route_score,

            Source:
              route.traffic_source,
          })
        )
      );

      // ----------------------------------------------------------
      // 19. Update map/UI
      // ----------------------------------------------------------

      setRouteResult(
        finalRouteResult
      );

      // ----------------------------------------------------------
      // 20. Automatically switch to map
      //
      // This makes the route immediately visible after pressing
      // Calculate Route from any relevant UI location.
      // ----------------------------------------------------------

      setActiveTab("map");

      // ----------------------------------------------------------
      // 21. Optional intelligence message
      // ----------------------------------------------------------

      const recommendedRoute =
        finalRoutes.find(
          (route) =>
            route.recommended === true
        ) ||
        finalRoutes[0];

      if (
        recommendedRoute &&
        recommendedRoute.live_eta_min !==
          undefined
      ) {
        console.log(
          `Recommended route: ${
            recommendedRoute.route_id
          } | ` +
          `Live ETA: ${
            recommendedRoute.live_eta_min
          } min | ` +
          `Traffic delay: ${
            recommendedRoute.traffic_delay_min
          } min`
        );
      }

    } catch (error) {
      // ----------------------------------------------------------
      // 22. Error handling
      // ----------------------------------------------------------

      console.error(
        "================================================"
      );

      console.error(
        "BENGALURU PULSE ROUTING ERROR"
      );

      console.error(
        "================================================"
      );

      console.error(
        error
      );

      // ----------------------------------------------------------
      // Backend error
      // ----------------------------------------------------------

      if (
        error.response &&
        error.response.data
      ) {
        console.error(
          "Backend response:",
          error.response.data
        );
      }

      let message =
        "Unable to calculate route.";

      if (
        error.response?.data?.detail
      ) {
        message =
          error.response.data.detail;
      } else if (
        error.message
      ) {
        message =
          error.message;
      }

      // ----------------------------------------------------------
      // Special handling for common failures
      // ----------------------------------------------------------

      if (
        error.code ===
        "ECONNABORTED"
      ) {
        message =
          "Routing request timed out. " +
          "Make sure OSRM and the FastAPI backend are running.";
      }

      if (
        error.code ===
        "ERR_NETWORK"
      ) {
        message =
          "Cannot connect to Bengaluru Pulse backend. " +
          "Start FastAPI and try again.";
      }

      alert(message);

      // Clear broken route
      setRouteResult(null);

    } finally {
      // ----------------------------------------------------------
      // 23. Stop loading state
      // ----------------------------------------------------------

      setRouteLoading(false);
    }
  };

  // ============================================================
  // TRAFFIC PREDICTION
  // ============================================================

  const predictTraffic = async () => {
    if (
      trafficVolume === "" ||
      averageSpeed === ""
    ) {
      alert(
        "Please enter Traffic Volume and Average Speed."
      );
      return;
    }

    const volume =
      Number(trafficVolume);

    const speed =
      Number(averageSpeed);

    if (
      volume < 0 ||
      volume > 500
    ) {
      alert(
        "Traffic Volume must be between 0 and 500."
      );
      return;
    }

    if (
      speed < 0 ||
      speed > 120
    ) {
      alert(
        "Average Speed must be between 0 and 120 km/h."
      );
      return;
    }

    setPredLoading(true);

    try {
      const response =
        await axios.post(
          `${API_BASE_URL}/predict`,
          {
            location,
            traffic_volume:
              parseInt(
                trafficVolume,
                10
              ),
            average_speed:
              parseFloat(
                averageSpeed
              ),
            weather,
          }
        );

      const data =
        response.data;

      setPredResult(data);

      await fetchHistory();
      await fetchDashboard();

      generateMemoryInsight([
        ...history,
        {
          location,
          prediction:
            data.predicted_congestion,
          weather,
          trafficVolume,
          averageSpeed,
        },
      ]);
    } catch (error) {
      console.error(
        "Prediction failed:",
        error
      );

      const message =
        error.response?.data
          ?.detail ||
        "Prediction failed. Is the backend running?";

      alert(message);
    } finally {
      setPredLoading(false);
    }
  };

  // ============================================================
  // PREDICTION VALUES
  // ============================================================

  const predValue =
    Number(
      predResult?.predicted_congestion
    ) || 0;

  const predStatus =
    predResult?.traffic_status ||
    null;

  const statusColor =
    predStatus &&
    STATUS_COLORS[predStatus]
      ? STATUS_COLORS[predStatus]
      : "#888";

  const predictionCount =
    dashboardData?.analytics
      ?.total_predictions ??
    history.length;

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <div className="app-root">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="app-header">

        <div className="header-brand">

          <span className="brand-icon">
            🚦
          </span>

          <div>
            <h1 className="brand-title">
              Bengaluru Pulse
            </h1>

            <p className="brand-sub">
              AI-Powered Urban Traffic
              Intelligence System
            </p>
          </div>

        </div>

        <div className="header-controls">

          <div className="weather-selector">

            {WEATHER_OPTIONS.map(
              (item) => (
                <button
                  key={item}
                  className={`weather-btn ${
                    weather === item
                      ? "active"
                      : ""
                  }`}
                  onClick={() =>
                    setWeather(item)
                  }
                >
                  {item === "Sunny"
                    ? "☀️"
                    : item === "Cloudy"
                    ? "☁️"
                    : "🌧️"}{" "}
                  {item}
                </button>
              )
            )}

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
            label:
              "City Avg Congestion",
            value:
              hotspotMeta.cityAvg !==
              undefined
                ? Number(
                    hotspotMeta.cityAvg
                  ).toFixed(1)
                : "--",
            icon: "📊",
            color: "#00bfff",
          },

          {
            label:
              "Worst Hotspot",
            value:
              hotspotMeta.worst ||
              "--",
            icon: "🔴",
            color: "#ff3333",
          },

          {
            label:
              "Best Location",
            value:
              hotspotMeta.best ||
              "--",
            icon: "🟢",
            color: "#00ff99",
          },

          {
            label:
              "Predictions Made",
            value:
              predictionCount,
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
            label:
              "Active Alerts",
            value:
              hotspots.filter(
                (item) =>
                  item.status ===
                    "SEVERE" ||
                  item.status ===
                    "HIGH"
              ).length +
              incidents.length,
            icon: "⚠️",
            color: "#ff8800",
          },
        ].map(
          (kpi, index) => (
            <motion.div
              key={kpi.label}
              className="kpi-card"
              initial={{
                opacity: 0,
                y: 20,
              }}
              animate={{
                opacity: 1,
                y: 0,
              }}
              transition={{
                delay:
                  index * 0.06,
              }}
              style={{
                "--accent":
                  kpi.color,
              }}
            >

              <div className="kpi-icon">
                {kpi.icon}
              </div>

              <div
                className="kpi-value"
                style={{
                  color:
                    kpi.color,
                }}
              >
                {kpi.value}
              </div>

              <div className="kpi-label">
                {kpi.label}
              </div>

            </motion.div>
          )
        )}

      </div>

      {/* ======================================================
          NAVIGATION
      ====================================================== */}

      <nav className="tab-nav">

        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${
              activeTab === tab.id
                ? "active"
                : ""
            }`}
            onClick={() =>
              setActiveTab(tab.id)
            }
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
          initial={{
            opacity: 0,
            y: 16,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          exit={{
            opacity: 0,
            y: -16,
          }}
          transition={{
            duration: 0.25,
          }}
        >

          {/* ==================================================
              DASHBOARD
          ================================================== */}

          {activeTab ===
            "dashboard" && (
            <div className="dashboard-grid">

              {/* PREDICTION */}

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
                  onChange={(
                    event
                  ) =>
                    setLocation(
                      event.target.value
                    )
                  }
                >

                  {LOCATIONS.map(
                    (item) => (
                      <option
                        key={item}
                      >
                        {item}
                      </option>
                    )
                  )}

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
                  value={
                    trafficVolume
                  }
                  onChange={(
                    event
                  ) =>
                    setTrafficVolume(
                      event.target.value
                    )
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
                  value={
                    averageSpeed
                  }
                  onChange={(
                    event
                  ) =>
                    setAverageSpeed(
                      event.target.value
                    )
                  }
                />

                <button
                  className="predict-btn"
                  onClick={
                    predictTraffic
                  }
                  disabled={
                    predLoading
                  }
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
                      "--status-color":
                        statusColor,
                    }}
                  >

                    <div className="pred-result-label">
                      Congestion Index
                    </div>

                    <div
                      className="pred-result-value"
                      style={{
                        color:
                          statusColor,
                      }}
                    >
                      {predValue.toFixed(
                        1
                      )}
                    </div>

                    <div
                      className="pred-result-status"
                      style={{
                        color:
                          statusColor,
                      }}
                    >
                      {predResult.signal ===
                      "GREEN"
                        ? "🟢"
                        : predResult.signal ===
                          "YELLOW"
                        ? "🟡"
                        : "🔴"}{" "}
                      {predStatus}
                    </div>

                    <div className="pred-delay">

                      ⏱ Est. delay:{" "}

                      {
                        predResult.estimated_delay_minutes
                      }{" "}
                      min

                    </div>

                  </motion.div>
                )}

              </div>

              {/* GAUGE */}

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
                        color:
                          "#00bfff",
                        marginRight:
                          "6px",
                      }}
                    />

                    {
                      predResult.recommendation
                    }

                  </div>
                )}

              </div>

              {/* EXPLAINABLE AI */}

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
                      key:
                        "Traffic Volume",
                      val:
                        trafficVolume ||
                        "--",
                    },

                    {
                      key:
                        "Avg Speed",
                      val:
                        averageSpeed
                          ? `${averageSpeed} km/h`
                          : "--",
                    },

                    {
                      key:
                        "Density",
                      val:
                        predResult
                          ? `${Math.min(
                              predValue *
                                4,
                              100
                            ).toFixed(
                              0
                            )}%`
                          : "--",
                    },

                    {
                      key:
                        "Status",
                      val:
                        predStatus ||
                        "--",
                      color:
                        statusColor,
                    },
                  ].map(
                    (item) => (
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
                              item.color ||
                              "#fff",
                          }}
                        >
                          {item.val}
                        </span>

                      </div>
                    )
                  )}

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

              {/* ANALYTICS */}

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
                        style={{
                          color:
                            "#00bfff",
                        }}
                      >
                        {
                          analytics.daily_avg_congestion
                        }
                      </div>

                      <div className="stat-lbl">
                        Daily Average
                      </div>

                    </div>

                    <div className="stat-block">

                      <div
                        className="stat-val"
                        style={{
                          color:
                            "#ff8800",
                        }}
                      >
                        {
                          analytics.risk_score
                        }
                      </div>

                      <div className="stat-lbl">
                        Risk Score
                      </div>

                    </div>

                    <div className="stat-block">

                      <div
                        className="stat-val"
                        style={{
                          color:
                            "#ff3333",
                        }}
                      >
                        {
                          analytics
                            .congestion_distribution
                            ?.SEVERE ??
                          0
                        }
                        h
                      </div>

                      <div className="stat-lbl">
                        Severe Hours
                      </div>

                    </div>

                    <div className="stat-block">

                      <div
                        className="stat-val"
                        style={{
                          color:
                            "#00ff99",
                        }}
                      >
                        {
                          analytics
                            .congestion_distribution
                            ?.LOW ??
                          0
                        }
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
                        fontSize:
                          "12px",
                        color:
                          "#aaa",
                        marginBottom:
                          "6px",
                      }}
                    >
                      Top Peak Hours
                    </div>

                    {analytics.top_peak_hours?.map(
                      (peak) => (
                        <div
                          key={
                            peak.hour
                          }
                          className="peak-row"
                        >

                          <span
                            style={{
                              color:
                                "#ddd",
                            }}
                          >
                            {
                              peak.label
                            }
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
                            ).toFixed(
                              1
                            )}{" "}
                            —{" "}
                            {
                              peak.status
                            }
                          </span>

                        </div>
                      )
                    )}

                  </div>

                </div>
              )}

              {/* DATABASE HISTORY */}

              <div className="glass-card analytics-card">

                <h2 className="card-title">

                  <FaHistory />

                  Prediction History

                </h2>

                {historyLoading ? (
                  <div
                    style={{
                      color:
                        "#aaa",
                      padding:
                        "20px 0",
                    }}
                  >
                    Loading prediction history...
                  </div>
                ) : history.length ===
                  0 ? (
                  <div
                    style={{
                      color:
                        "#aaa",
                      padding:
                        "20px 0",
                    }}
                  >
                    No predictions stored yet.
                  </div>
                ) : (
                  <div
                    style={{
                      overflowX:
                        "auto",
                    }}
                  >

                    <table
                      style={{
                        width:
                          "100%",
                        borderCollapse:
                          "collapse",
                      }}
                    >

                      <thead>

                        <tr
                          style={{
                            color:
                              "#aaa",
                            textAlign:
                              "left",
                          }}
                        >

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Location
                          </th>

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Congestion
                          </th>

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Status
                          </th>

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Weather
                          </th>

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Volume
                          </th>

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Speed
                          </th>

                          <th
                            style={{
                              padding:
                                "10px",
                            }}
                          >
                            Time
                          </th>

                        </tr>

                      </thead>

                      <tbody>

                        {history
                          .slice(
                            0,
                            10
                          )
                          .map(
                            (
                              item,
                              index
                            ) => {

                              const color =
                                STATUS_COLORS[
                                  item
                                    .trafficStatus
                                ] ||
                                "#00bfff";

                              return (
                                <tr
                                  key={
                                    item.id ||
                                    `${item.location}-${item.time}-${index}`
                                  }
                                >

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color:
                                        "#ddd",
                                    }}
                                  >
                                    {
                                      item.location
                                    }
                                  </td>

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color,
                                    }}
                                  >
                                    {Number(
                                      item.prediction
                                    ).toFixed(
                                      2
                                    )}
                                  </td>

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color,
                                    }}
                                  >
                                    {
                                      item.trafficStatus ||
                                      "--"
                                    }
                                  </td>

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color:
                                        "#ddd",
                                    }}
                                  >
                                    {
                                      item.weather ||
                                      "--"
                                    }
                                  </td>

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color:
                                        "#ddd",
                                    }}
                                  >
                                    {
                                      item.trafficVolume ??
                                      "--"
                                    }
                                  </td>

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color:
                                        "#ddd",
                                    }}
                                  >
                                    {
                                      item.averageSpeed ??
                                      "--"
                                    }{" "}
                                    km/h
                                  </td>

                                  <td
                                    style={{
                                      padding:
                                        "10px",
                                      color:
                                        "#aaa",
                                    }}
                                  >
                                    {
                                      item.time ||
                                      "--"
                                    }
                                  </td>

                                </tr>
                              );
                            }
                          )}

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

                    {/* ==================================================
              LIVE MAP + INTELLIGENT ROUTING
          ================================================== */}

          {activeTab === "map" && (
            <div className="map-layout">

              {/* ==================================================
                  MAIN MAP AREA
              ================================================== */}

              <div className="glass-card map-main-card">

                <h2 className="card-title">

                  <FaMapMarkedAlt />

                  Bengaluru Live Traffic & Predictive Routing

                </h2>

                {/* ==================================================
                    ROUTE PLANNER
                ================================================== */}

                <RoutePlanner
                  originText={originText}
                  destinationText={destinationText}
                  setOriginText={setOriginText}
                  setDestinationText={setDestinationText}
                  vehicle={vehicle}
                  setVehicle={setVehicle}
                  onCalculate={calculateRoute}
                  loading={routeLoading}
                />

                {/* ==================================================
                    ROUTE STATUS
                ================================================== */}

                {routeLoading && (
                  <div
                    style={{
                      marginTop: "14px",
                      padding: "12px 16px",
                      borderRadius: "10px",
                      background:
                        "rgba(0,191,255,0.08)",
                      border:
                        "1px solid rgba(0,191,255,0.25)",
                      color: "#00bfff",
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      fontSize: "13px",
                    }}
                  >
                    <span className="spinner" />

                    <span>
                      Calculating intelligent routes using
                      Bengaluru road network and live traffic...
                    </span>
                  </div>
                )}

                {/* ==================================================
                    MAP
                ================================================== */}

                <div className="map-wrapper">

                  <TrafficMap
                    hotspots={hotspots}
                    selectedLocation={location}
                    onLocationSelect={setLocation}
                    liveTraffic={liveTraffic}
                    liveTrafficLoading={
                      liveTrafficLoading
                    }
                    routeResult={routeResult}
                    routeLoading={routeLoading}
                  />

                </div>

                {/* ==================================================
                    ROUTE INTELLIGENCE
                ================================================== */}

                {routeResult?.routes?.length > 0 && (

                  <div
                    style={{
                      marginTop: "18px",
                    }}
                  >

                    {/* ------------------------------------------------
                        ROUTE HEADER
                    ------------------------------------------------ */}

                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: "10px",
                        marginBottom: "14px",
                      }}
                    >

                      <div>

                        <h3
                          style={{
                            margin: 0,
                            color: "#fff",
                            fontSize: "18px",
                          }}
                        >
                          <FaRoute
                            style={{
                              marginRight: "8px",
                              color: "#00bfff",
                            }}
                          />

                          Route Intelligence
                        </h3>

                        <div
                          style={{
                            marginTop: "5px",
                            color: "#888",
                            fontSize: "12px",
                          }}
                        >
                          {originText}
                          {" → "}
                          {destinationText}
                        </div>

                      </div>

                      <div
                        style={{
                          display: "flex",
                          gap: "8px",
                          flexWrap: "wrap",
                        }}
                      >

                        {/* ROUTING SOURCE */}

                        <span
                          style={{
                            padding:
                              "6px 10px",
                            borderRadius:
                              "999px",
                            background:
                              "rgba(0,191,255,0.10)",
                            border:
                              "1px solid rgba(0,191,255,0.25)",
                            color:
                              "#00bfff",
                            fontSize:
                              "11px",
                          }}
                        >
                          Routing:{" "}
                          {String(
                            routeResult.source ||
                              "OSRM"
                          ).toUpperCase()}
                        </span>

                        {/* VEHICLE */}

                        <span
                          style={{
                            padding:
                              "6px 10px",
                            borderRadius:
                              "999px",
                            background:
                              "rgba(255,255,255,0.06)",
                            border:
                              "1px solid rgba(255,255,255,0.12)",
                            color:
                              "#ddd",
                            fontSize:
                              "11px",
                          }}
                        >
                          Vehicle:{" "}
                          {String(
                            routeResult.vehicle ||
                              vehicle
                          ).toUpperCase()}
                        </span>

                      </div>

                    </div>

                    {/* ------------------------------------------------
                        ROUTE CARDS
                    ------------------------------------------------ */}

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns:
                          "repeat(auto-fit, minmax(250px, 1fr))",
                        gap: "12px",
                      }}
                    >

                      {routeResult.routes.map(
                        (route, index) => {

                          const recommended =
                            route.recommended ===
                            true;

                          const trafficStatus =
                            route.traffic_status ||
                            "UNKNOWN";

                          const statusColor =
                            trafficStatus ===
                            "SEVERE"
                              ? "#ff3333"
                              : trafficStatus ===
                                "HIGH"
                              ? "#ff8800"
                              : trafficStatus ===
                                "MODERATE"
                              ? "#ffcc00"
                              : trafficStatus ===
                                "LOW"
                              ? "#00ff99"
                              : "#888";

                          const liveEta =
                            Number(
                              route.live_eta_min
                            );

                          const baseEta =
                            Number(
                              route.base_eta_min
                            );

                          const delay =
                            Number(
                              route.traffic_delay_min
                            );

                          const distance =
                            Number(
                              route.distance_km
                            );

                          const score =
                            Number(
                              route.route_score
                            );

                          return (

                            <motion.div
                              key={
                                route.route_id ||
                                `route-${index}`
                              }

                              initial={{
                                opacity: 0,
                                y: 10,
                              }}

                              animate={{
                                opacity: 1,
                                y: 0,
                              }}

                              transition={{
                                delay:
                                  index * 0.08,
                              }}

                              style={{
                                position:
                                  "relative",

                                padding:
                                  "16px",

                                borderRadius:
                                  "14px",

                                background:
                                  recommended
                                    ? "rgba(0,191,255,0.08)"
                                    : "rgba(255,255,255,0.035)",

                                border:
                                  recommended
                                    ? "1px solid rgba(0,191,255,0.45)"
                                    : "1px solid rgba(255,255,255,0.10)",

                                boxShadow:
                                  recommended
                                    ? "0 0 20px rgba(0,191,255,0.08)"
                                    : "none",
                              }}
                            >

                              {/* ====================================
                                  RECOMMENDED BADGE
                              ==================================== */}

                              {recommended && (

                                <div
                                  style={{
                                    position:
                                      "absolute",

                                    top: "-9px",

                                    right: "12px",

                                    padding:
                                      "4px 9px",

                                    borderRadius:
                                      "999px",

                                    background:
                                      "#00bfff",

                                    color:
                                      "#001018",

                                    fontSize:
                                      "10px",

                                    fontWeight:
                                      "700",

                                    letterSpacing:
                                      "0.5px",
                                  }}
                                >
                                  RECOMMENDED
                                </div>

                              )}

                              {/* ====================================
                                  ROUTE TITLE
                              ==================================== */}

                              <div
                                style={{
                                  display:
                                    "flex",

                                  justifyContent:
                                    "space-between",

                                  alignItems:
                                    "center",

                                  marginBottom:
                                    "12px",
                                }}
                              >

                                <div
                                  style={{
                                    color:
                                      "#fff",

                                    fontWeight:
                                      "700",

                                    fontSize:
                                      "14px",
                                  }}
                                >
                                  Route {index + 1}
                                </div>

                                <div
                                  style={{
                                    color:
                                      statusColor,

                                    fontSize:
                                      "11px",

                                    fontWeight:
                                      "700",
                                  }}
                                >
                                  {trafficStatus}
                                </div>

                              </div>

                              {/* ====================================
                                  PRIMARY METRICS
                              ==================================== */}

                              <div
                                style={{
                                  display:
                                    "grid",

                                  gridTemplateColumns:
                                    "1fr 1fr",

                                  gap:
                                    "10px",

                                  marginBottom:
                                    "12px",
                                }}
                              >

                                {/* ETA */}

                                <div
                                  style={{
                                    padding:
                                      "10px",

                                    borderRadius:
                                      "10px",

                                    background:
                                      "rgba(0,0,0,0.18)",
                                  }}
                                >

                                  <div
                                    style={{
                                      color:
                                        "#888",

                                      fontSize:
                                        "10px",

                                      marginBottom:
                                        "4px",
                                    }}
                                  >
                                    LIVE ETA
                                  </div>

                                  <div
                                    style={{
                                      color:
                                        "#00bfff",

                                      fontSize:
                                        "21px",

                                      fontWeight:
                                        "700",
                                    }}
                                  >
                                    {Number.isFinite(
                                      liveEta
                                    )
                                      ? liveEta.toFixed(
                                          1
                                        )
                                      : "--"}

                                    <span
                                      style={{
                                        fontSize:
                                          "11px",

                                        marginLeft:
                                          "3px",

                                        color:
                                          "#aaa",
                                      }}
                                    >
                                      min
                                    </span>
                                  </div>

                                </div>

                                {/* DISTANCE */}

                                <div
                                  style={{
                                    padding:
                                      "10px",

                                    borderRadius:
                                      "10px",

                                    background:
                                      "rgba(0,0,0,0.18)",
                                  }}
                                >

                                  <div
                                    style={{
                                      color:
                                        "#888",

                                      fontSize:
                                        "10px",

                                      marginBottom:
                                        "4px",
                                    }}
                                  >
                                    DISTANCE
                                  </div>

                                  <div
                                    style={{
                                      color:
                                        "#fff",

                                      fontSize:
                                        "18px",

                                      fontWeight:
                                        "700",
                                    }}
                                  >
                                    {Number.isFinite(
                                      distance
                                    )
                                      ? distance.toFixed(
                                          2
                                        )
                                      : "--"}

                                    <span
                                      style={{
                                        fontSize:
                                          "11px",

                                        marginLeft:
                                          "3px",

                                        color:
                                          "#aaa",
                                      }}
                                    >
                                      km
                                    </span>
                                  </div>

                                </div>

                              </div>

                              {/* ====================================
                                  ETA BREAKDOWN
                              ==================================== */}

                              <div
                                style={{
                                  display:
                                    "flex",

                                  flexDirection:
                                    "column",

                                  gap:
                                    "7px",

                                  fontSize:
                                    "12px",
                                }}
                              >

                                <div
                                  style={{
                                    display:
                                      "flex",

                                    justifyContent:
                                      "space-between",

                                    color:
                                      "#aaa",
                                  }}
                                >

                                  <span>
                                    Base ETA
                                  </span>

                                  <span
                                    style={{
                                      color:
                                        "#ddd",
                                    }}
                                  >
                                    {Number.isFinite(
                                      baseEta
                                    )
                                      ? `${baseEta.toFixed(
                                          1
                                        )} min`
                                      : "--"}
                                  </span>

                                </div>

                                <div
                                  style={{
                                    display:
                                      "flex",

                                    justifyContent:
                                      "space-between",

                                    color:
                                      "#aaa",
                                  }}
                                >

                                  <span>
                                    Traffic Delay
                                  </span>

                                  <span
                                    style={{
                                      color:
                                        delay > 0
                                          ? "#ff8800"
                                          : "#00ff99",
                                    }}
                                  >
                                    {Number.isFinite(
                                      delay
                                    )
                                      ? `+${delay.toFixed(
                                          1
                                        )} min`
                                      : "--"}
                                  </span>

                                </div>

                                <div
                                  style={{
                                    display:
                                      "flex",

                                    justifyContent:
                                      "space-between",

                                    color:
                                      "#aaa",
                                  }}
                                >

                                  <span>
                                    Route Score
                                  </span>

                                  <span
                                    style={{
                                      color:
                                        "#bb66ff",
                                    }}
                                  >
                                    {Number.isFinite(
                                      score
                                    )
                                      ? score.toFixed(
                                          2
                                        )
                                      : "--"}
                                  </span>

                                </div>

                              </div>

                              {/* ====================================
                                  SOURCE
                              ==================================== */}

                              <div
                                style={{
                                  marginTop:
                                    "12px",

                                  paddingTop:
                                    "10px",

                                  borderTop:
                                    "1px solid rgba(255,255,255,0.08)",

                                  display:
                                    "flex",

                                  justifyContent:
                                    "space-between",

                                  alignItems:
                                    "center",

                                  gap:
                                    "8px",
                                }}
                              >

                                <span
                                  style={{
                                    color:
                                      "#777",

                                    fontSize:
                                      "10px",
                                  }}
                                >
                                  Traffic Source
                                </span>

                                <span
                                  style={{
                                    color:
                                      "#aaa",

                                    fontSize:
                                      "10px",

                                    fontWeight:
                                      "600",
                                  }}
                                >
                                  {route.traffic_source ||
                                    "OSRM"}
                                </span>

                              </div>

                              {/* ====================================
                                  INTELLIGENCE STATUS
                              ==================================== */}

                              <div
                                style={{
                                  marginTop:
                                    "8px",

                                  display:
                                    "flex",

                                  alignItems:
                                    "center",

                                  gap:
                                    "6px",

                                  color:
                                    route.intelligence_available
                                      ? "#00ff99"
                                      : "#888",

                                  fontSize:
                                    "10px",
                                }}
                              >

                                <span>
                                  {route.intelligence_available
                                    ? "●"
                                    : "○"}
                                </span>

                                <span>
                                  {route.intelligence_available
                                    ? "Live traffic intelligence active"
                                    : "Base routing only"}
                                </span>

                              </div>

                            </motion.div>

                          );
                        }
                      )}

                    </div>

                  </div>

                )}

              </div>

              {/* ==================================================
                  RIGHT SIDEBAR
              ================================================== */}

              <div className="glass-card map-sidebar">

                {/* ==================================================
                    LOCATION DETAILS
                ================================================== */}

                <h2 className="card-title">
                  Location Details
                </h2>

                <div className="location-list">

                  {LOCATIONS.map(
                    (loc) => {

                      const spot =
                        hotspots.find(
                          (item) =>
                            item.location ===
                            loc
                        );

                      const color =
                        spot
                          ? STATUS_COLORS[
                              spot.status
                            ] ||
                            "#888"
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
                            setLocation(
                              loc
                            )
                          }

                          style={{
                            "--accent":
                              color,
                          }}
                        >

                          <div
                            className="loc-dot"

                            style={{
                              background:
                                color,

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

                    }
                  )}

                </div>

                {/* ==================================================
                    CURRENT ROUTE SUMMARY
                ================================================== */}

                {routeResult?.routes?.length > 0 && (

                  <div
                    style={{
                      marginTop: "22px",
                      paddingTop: "18px",
                      borderTop:
                        "1px solid rgba(255,255,255,0.08)",
                    }}
                  >

                    <h3
                      style={{
                        margin:
                          "0 0 12px",
                        color: "#fff",
                        fontSize: "14px",
                      }}
                    >
                      Current Journey
                    </h3>

                    <div
                      style={{
                        display: "flex",
                        flexDirection:
                          "column",
                        gap: "8px",
                      }}
                    >

                      <div
                        style={{
                          display: "flex",
                          justifyContent:
                            "space-between",
                          fontSize: "12px",
                        }}
                      >

                        <span
                          style={{
                            color: "#888",
                          }}
                        >
                          From
                        </span>

                        <span
                          style={{
                            color: "#ddd",
                            textAlign: "right",
                            maxWidth: "65%",
                          }}
                        >
                          {originText}
                        </span>

                      </div>

                      <div
                        style={{
                          display: "flex",
                          justifyContent:
                            "space-between",
                          fontSize: "12px",
                        }}
                      >

                        <span
                          style={{
                            color: "#888",
                          }}
                        >
                          To
                        </span>

                        <span
                          style={{
                            color: "#ddd",
                            textAlign: "right",
                            maxWidth: "65%",
                          }}
                        >
                          {destinationText}
                        </span>

                      </div>

                      <div
                        style={{
                          display: "flex",
                          justifyContent:
                            "space-between",
                          fontSize: "12px",
                        }}
                      >

                        <span
                          style={{
                            color: "#888",
                          }}
                        >
                          Alternatives
                        </span>

                        <span
                          style={{
                            color: "#00bfff",
                            fontWeight: "700",
                          }}
                        >
                          {routeResult.routes.length}
                        </span>

                      </div>

                    </div>

                  </div>

                )}

              </div>

            </div>
          )}

          {/* ==================================================
              FORECAST
          ================================================== */}

          {activeTab ===
            "forecast" && (
            <div className="full-card-layout">

              <div
                className="glass-card"
                style={{
                  padding: "28px",
                }}
              >

                <div className="forecast-location-row">

                  <h2
                    className="card-title"
                    style={{
                      marginBottom:
                        0,
                    }}
                  >

                    <FaChartLine />

                    12-Hour Forecast

                  </h2>

                  <select
                    className="field-input compact-select"
                    value={location}
                    onChange={(
                      event
                    ) =>
                      setLocation(
                        event.target.value
                      )
                    }
                  >

                    {LOCATIONS.map(
                      (item) => (
                        <option
                          key={item}
                        >
                          {item}
                        </option>
                      )
                    )}

                  </select>

                </div>

                <ForecastPanel
                  forecast={
                    forecast?.forecast
                  }
                  location={
                    forecast?.location
                  }
                  peakCongestion={
                    forecast?.peak_congestion
                  }
                  bestWindow={
                    forecast?.best_travel_window
                  }
                />

                {forecast?.summary && (
                  <div className="forecast-summary">
                    💡{" "}
                    {
                      forecast.summary
                    }
                  </div>
                )}

              </div>

            </div>
          )}

          {/* ==================================================
              HOTSPOTS
          ================================================== */}

          {activeTab ===
            "hotspots" && (
            <div className="full-card-layout">

              <div
                className="glass-card"
                style={{
                  padding: "28px",
                }}
              >

                <h2 className="card-title">

                  <FaBell />

                  Congestion Hotspot Heatmap

                </h2>

                <HotspotHeatmap
                  hotspots={
                    hotspots
                  }
                  cityAverage={
                    hotspotMeta.cityAvg
                  }
                />

              </div>

            </div>
          )}

          {/* ==================================================
              HISTORICAL TRENDS
          ================================================== */}

          {activeTab ===
            "trends" && (
            <div className="full-card-layout">

              <div
                className="glass-card"
                style={{
                  padding: "28px",
                }}
              >

                <h2 className="card-title">

                  <FaHistory />

                  Historical Trends

                </h2>

                <HistoricalTrends
                  trendData={
                    trends?.trend_data
                  }
                  locations={
                    trends?.locations
                  }
                  cityTrend={
                    trends?.city_trend
                  }
                />

                {trends && (
                  <div className="trends-footer">

                    <span>

                      Most congested today:{" "}

                      <strong
                        style={{
                          color:
                            "#ff3333",
                        }}
                      >
                        {
                          trends.most_congested_today
                        }
                      </strong>

                    </span>

                    <span>

                      Least congested today:{" "}

                      <strong
                        style={{
                          color:
                            "#00ff99",
                        }}
                      >
                        {
                          trends.least_congested_today
                        }
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

          {activeTab ===
            "commute" && (
            <div className="commute-layout">

              <div
                className="glass-card commute-card"
                style={{
                  padding: "28px",
                }}
              >

                <CommuteAdvisor
                  locations={
                    LOCATIONS
                  }
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
                ].map(
                  (item, index) => (
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
                        delay:
                          index *
                          0.08,
                      }}
                    >

                      <span className="tip-icon">
                        {item.icon}
                      </span>

                      <span className="tip-text">
                        {item.tip}
                      </span>

                    </motion.div>
                  )
                )}

              </div>

            </div>
          )}

        </motion.div>

      </AnimatePresence>

      {/* ======================================================
          FOOTER
      ====================================================== */}

      <footer className="app-footer">

        <FaRoad />

        Bengaluru Pulse

        &nbsp;•&nbsp;

        AI Urban Traffic Intelligence System

        &nbsp;•&nbsp;

        Mem-Brain Engine Active

      </footer>

    </div>
  );
}

export default App;
