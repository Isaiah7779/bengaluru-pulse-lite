import React, { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import {
  FaClock,
  FaMapMarkerAlt,
  FaRoute,
  FaCheckCircle,
  FaCar,
  FaRoad,
  FaBolt,
} from "react-icons/fa";
import { API_BASE_URL, STATUS_COLORS } from "../config";

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
      const response = await axios.post(
        `${API_BASE_URL}/commute-advisor`,
        {
          origin,
          destination,
          preferred_arrival: arrivalTime,
        }
      );

      setResult(response.data);
    } catch (error) {
      console.error("Commute Advisor Error:", error);

      if (error.response) {
        console.error("Server response:", error.response.data);
      }

      alert("Failed to fetch commute advice");
    } finally {
      setLoading(false);
    }
  };

  /*
   * ------------------------------------------------------------
   * Helper functions
   * ------------------------------------------------------------
   */

  const formatMinutes = (value) => {
    if (value === undefined || value === null || value === "") {
      return "--";
    }

    const number = Number(value);

    if (Number.isNaN(number)) {
      return String(value);
    }

    return `${number.toFixed(number % 1 === 0 ? 0 : 1)} min`;
  };

  const getStatusColor = (status) => {
    if (!status) return "#aaa";

    return (
      STATUS_COLORS[status] ||
      STATUS_COLORS[String(status).toUpperCase()] ||
      "#aaa"
    );
  };

  const getRouteName = (route, index) => {
    if (route?.route) {
      return route.route;
    }

    if (route?.name) {
      return route.name;
    }

    return index === 0
      ? "Recommended Route"
      : `Alternative Route ${index}`;
  };

  const getRouteType = (route) => {
    if (route?.type) {
      return route.type;
    }

    if (route?.mode) {
      return route.mode;
    }

    return "Live Traffic Route";
  };

  const getTravelTime = (route) => {
    return (
      route?.travel_time_minutes ??
      route?.estimated_travel_minutes ??
      route?.travel_time ??
      route?.duration_minutes ??
      null
    );
  };

  const getDelay = (route) => {
    return (
      route?.delay_minutes ??
      route?.traffic_delay_minutes ??
      route?.delay ??
      null
    );
  };

  const getDistance = (route) => {
    return (
      route?.distance_km ??
      route?.distance ??
      route?.length_km ??
      null
    );
  };

  const getTrafficCondition = (route) => {
    return (
      route?.traffic_condition ??
      route?.status ??
      route?.traffic_status ??
      null
    );
  };

  const getRouteReason = (route) => {
    return (
      route?.recommended_for ??
      route?.reason ??
      route?.description ??
      "Based on current traffic conditions"
    );
  };

  const routeAlternatives = result?.route_alternatives || [];

  /*
   * Find the recommended route.
   *
   * Prefer an explicitly recommended route.
   * Otherwise use the first route.
   */
  const recommendedRoute =
    routeAlternatives.find(
      (route) =>
        route?.recommended === true ||
        route?.is_recommended === true ||
        route?.selected === true
    ) || routeAlternatives[0];

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* --------------------------------------------------------
          HEADER
      --------------------------------------------------------- */}

      <div style={{ marginBottom: "16px" }}>
        <div
          style={{
            fontSize: "15px",
            color: "#e8eef7",
            marginBottom: "4px",
          }}
        >
          <FaRoute
            style={{
              marginRight: "7px",
              color: "#00bfff",
            }}
          />

          <strong>AI Commute Advisor</strong>
        </div>

        <div
          style={{
            fontSize: "12px",
            color: "#8fa2b8",
          }}
        >
          Get optimal departure time and route recommendations
        </div>
      </div>

      {/* --------------------------------------------------------
          ORIGIN + DESTINATION
      --------------------------------------------------------- */}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "12px",
          marginBottom: "16px",
        }}
      >
        {/* Origin */}

        <div>
          <label style={labelStyle}>
            <FaMapMarkerAlt
              style={{
                color: "#00bfff",
                marginRight: "5px",
              }}
            />

            Origin
          </label>

          <select
            value={origin}
            onChange={(event) => setOrigin(event.target.value)}
            style={selectStyle}
          >
            {locations.map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </select>
        </div>

        {/* Destination */}

        <div>
          <label style={labelStyle}>
            <FaMapMarkerAlt
              style={{
                color: "#ff3333",
                marginRight: "5px",
              }}
            />

            Destination
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

      {/* --------------------------------------------------------
          ARRIVAL TIME
      --------------------------------------------------------- */}

      <div style={{ marginBottom: "16px" }}>
        <label style={labelStyle}>
          <FaClock
            style={{
              marginRight: "5px",
              color: "#aaa",
            }}
          />

          Preferred Arrival Time
        </label>

        <input
          type="time"
          value={arrivalTime}
          onChange={(event) => setArrivalTime(event.target.value)}
          style={inputStyle}
        />
      </div>

      {/* --------------------------------------------------------
          BUTTON
      --------------------------------------------------------- */}

      <button
        onClick={fetchAdvice}
        disabled={loading}
        style={{
          ...buttonStyle,
          opacity: loading ? 0.7 : 1,
          cursor: loading ? "wait" : "pointer",
        }}
      >
        {loading ? (
          <>
            <span style={{ marginRight: "8px" }}>Analyzing traffic...</span>
          </>
        ) : (
          <>
            <FaBolt style={{ marginRight: "7px" }} />
            Get Commute Advice
          </>
        )}
      </button>

      {/* --------------------------------------------------------
          RESULTS
      --------------------------------------------------------- */}

      {result && (
        <motion.div
          initial={{
            opacity: 0,
            y: 10,
          }}
          animate={{
            opacity: 1,
            y: 0,
          }}
          style={{
            marginTop: "16px",
            flex: 1,
            overflowY: "auto",
            paddingRight: "3px",
          }}
        >
          {/* ----------------------------------------------------
              TRIP SUMMARY
          ----------------------------------------------------- */}

          <div style={tripHeaderStyle}>
            <div
              style={{
                fontSize: "13px",
                color: "#fff",
                fontWeight: "bold",
                marginBottom: "4px",
              }}
            >
              {result.origin || origin}
              <span
                style={{
                  color: "#00bfff",
                  margin: "0 8px",
                }}
              >
                →
              </span>
              {result.destination || destination}
            </div>

            <div
              style={{
                fontSize: "11px",
                color: "#8fa2b8",
              }}
            >
              Arrival target:{" "}
              <strong style={{ color: "#ddd" }}>
                {result.preferred_arrival || arrivalTime}
              </strong>
            </div>
          </div>

          {/* ----------------------------------------------------
              RECOMMENDATION
          ----------------------------------------------------- */}

          <div style={summaryStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "7px",
                marginBottom: "7px",
              }}
            >
              <FaCheckCircle
                style={{
                  color: "#00ff99",
                }}
              />

              <strong
                style={{
                  color: "#00ff99",
                  fontSize: "13px",
                }}
              >
                AI Recommendation
              </strong>
            </div>

            <div
              style={{
                color: "#ddd",
                fontSize: "12px",
                lineHeight: "1.5",
              }}
            >
              {result.advisory ||
                `Recommended departure is ${result.recommended_departure || "--"} for arrival by ${
                  result.preferred_arrival || arrivalTime
                }.`}
            </div>
          </div>

          {/* ----------------------------------------------------
              BEST DEPARTURE CARD
          ----------------------------------------------------- */}

          {result.recommended_departure && (
            <div style={bestDepartureStyle}>
              <div>
                <div
                  style={{
                    fontSize: "11px",
                    color: "#8fa2b8",
                    marginBottom: "3px",
                  }}
                >
                  BEST DEPARTURE
                </div>

                <div
                  style={{
                    fontSize: "25px",
                    fontWeight: "800",
                    color: "#00ff99",
                    lineHeight: "1.1",
                  }}
                >
                  {result.recommended_departure}
                </div>
              </div>

              {recommendedRoute && (
                <div
                  style={{
                    textAlign: "right",
                  }}
                >
                  <div
                    style={{
                      fontSize: "10px",
                      color: "#8fa2b8",
                      marginBottom: "4px",
                    }}
                  >
                    RECOMMENDED ROUTE
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: "bold",
                      color: "#fff",
                    }}
                  >
                    {getRouteName(
                      recommendedRoute,
                      0
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ----------------------------------------------------
              DEPARTURE OPTIONS
          ----------------------------------------------------- */}

          {result.departure_suggestions &&
            result.departure_suggestions.length > 0 && (
              <div
                style={{
                  marginBottom: "14px",
                }}
              >
                <div style={sectionTitleStyle}>
                  <FaClock
                    style={{
                      color: "#00bfff",
                      marginRight: "6px",
                    }}
                  />

                  Departure Time Options
                </div>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "7px",
                  }}
                >
                  {result.departure_suggestions.map(
                    (suggestion, index) => {
                      const isRecommended =
                        suggestion.recommended === true ||
                        suggestion.departure_time ===
                          result.recommended_departure;

                      return (
                        <motion.div
                          key={`${suggestion.departure_time}-${index}`}
                          initial={{
                            opacity: 0,
                            x: -10,
                          }}
                          animate={{
                            opacity: 1,
                            x: 0,
                          }}
                          transition={{
                            delay: index * 0.05,
                          }}
                          style={{
                            background: isRecommended
                              ? "rgba(0,255,153,0.07)"
                              : "rgba(255,255,255,0.035)",

                            border: isRecommended
                              ? "1px solid rgba(0,255,153,0.65)"
                              : "1px solid rgba(255,255,255,0.1)",

                            borderRadius: "9px",
                            padding: "10px 12px",

                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <div>
                            <div
                              style={{
                                color: isRecommended
                                  ? "#00ff99"
                                  : "#ddd",
                                fontWeight: "bold",
                                fontSize: "14px",
                              }}
                            >
                              {suggestion.departure_time}
                            </div>

                            <div
                              style={{
                                color: "#8fa2b8",
                                fontSize: "11px",
                                marginTop: "3px",
                              }}
                            >
                              {suggestion.avg_route_congestion !==
                              undefined
                                ? `Congestion ${Number(
                                    suggestion.avg_route_congestion
                                  ).toFixed(1)}`
                                : suggestion.status ||
                                  "Traffic analysis"}
                            </div>
                          </div>

                          <div
                            style={{
                              textAlign: "right",
                            }}
                          >
                            {suggestion.estimated_travel_minutes !==
                              undefined && (
                              <div
                                style={{
                                  color: "#ddd",
                                  fontSize: "11px",
                                  marginBottom: "4px",
                                }}
                              >
                                {formatMinutes(
                                  suggestion.estimated_travel_minutes
                                )}
                              </div>
                            )}

                            {isRecommended && (
                              <div
                                style={{
                                  ...bestBadgeStyle,
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "4px",
                                }}
                              >
                                <FaCheckCircle />
                                BEST
                              </div>
                            )}
                          </div>
                        </motion.div>
                      );
                    }
                  )}
                </div>
              </div>
            )}

          {/* ----------------------------------------------------
              ROUTE ALTERNATIVES
          ----------------------------------------------------- */}

          {routeAlternatives.length > 0 && (
            <div>
              <div style={sectionTitleStyle}>
                <FaRoad
                  style={{
                    color: "#00bfff",
                    marginRight: "6px",
                  }}
                />

                Route Alternatives
              </div>

              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                }}
              >
                {routeAlternatives.map((route, index) => {
                  const routeName = getRouteName(
                    route,
                    index
                  );

                  const routeType =
                    getRouteType(route);

                  const travelTime =
                    getTravelTime(route);

                  const delay = getDelay(route);

                  const distance =
                    getDistance(route);

                  const traffic =
                    getTrafficCondition(route);

                  const isRecommended =
                    route === recommendedRoute ||
                    route?.recommended === true ||
                    route?.is_recommended === true;

                  const trafficColor =
                    getStatusColor(traffic);

                  return (
                    <motion.div
                      key={`${routeName}-${index}`}
                      initial={{
                        opacity: 0,
                        y: 8,
                      }}
                      animate={{
                        opacity: 1,
                        y: 0,
                      }}
                      transition={{
                        delay: index * 0.06,
                      }}
                      style={{
                        ...routeCardStyle,

                        border: isRecommended
                          ? "1px solid rgba(0,255,153,0.55)"
                          : "1px solid rgba(255,255,255,0.1)",

                        background: isRecommended
                          ? "rgba(0,255,153,0.055)"
                          : "rgba(255,255,255,0.035)",
                      }}
                    >
                      {/* Route title */}

                      <div
                        style={{
                          display: "flex",
                          justifyContent:
                            "space-between",
                          alignItems: "flex-start",
                          gap: "8px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "7px",
                            flexWrap: "wrap",
                          }}
                        >
                          <span
                            style={{
                              fontSize: "12px",
                              color: isRecommended
                                ? "#00ff99"
                                : "#00bfff",
                              fontWeight: "bold",
                            }}
                          >
                            {index === 0
                              ? "ROUTE"
                              : `ROUTE ${index + 1}`}
                          </span>

                          <strong
                            style={{
                              color: "#e6edf5",
                              fontSize: "12px",
                            }}
                          >
                            {routeName}
                          </strong>

                          {routeType && (
                            <span
                              style={
                                routeTypeStyle
                              }
                            >
                              {routeType}
                            </span>
                          )}
                        </div>

                        {isRecommended && (
                          <div
                            style={{
                              ...bestBadgeStyle,
                              flexShrink: 0,
                            }}
                          >
                            BEST
                          </div>
                        )}
                      </div>

                      {/* Route metrics */}

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns:
                            "repeat(3, 1fr)",
                          gap: "7px",
                          marginTop: "10px",
                        }}
                      >
                        {/* Travel time */}

                        <div style={metricStyle}>
                          <div
                            style={
                              metricLabelStyle
                            }
                          >
                            <FaClock
                              style={{
                                marginRight: "4px",
                              }}
                            />
                            TIME
                          </div>

                          <div
                            style={
                              metricValueStyle
                            }
                          >
                            {travelTime !== null
                              ? formatMinutes(
                                  travelTime
                                )
                              : "--"}
                          </div>
                        </div>

                        {/* Distance */}

                        <div style={metricStyle}>
                          <div
                            style={
                              metricLabelStyle
                            }
                          >
                            <FaRoute
                              style={{
                                marginRight: "4px",
                              }}
                            />
                            DISTANCE
                          </div>

                          <div
                            style={
                              metricValueStyle
                            }
                          >
                            {distance !== null
                              ? `${Number(
                                  distance
                                ).toFixed(1)} km`
                              : "--"}
                          </div>
                        </div>

                        {/* Delay */}

                        <div style={metricStyle}>
                          <div
                            style={
                              metricLabelStyle
                            }
                          >
                            <FaCar
                              style={{
                                marginRight: "4px",
                              }}
                            />
                            DELAY
                          </div>

                          <div
                            style={{
                              ...metricValueStyle,
                              color:
                                delay !== null
                                  ? delay > 10
                                    ? "#ff8800"
                                    : "#00ff99"
                                  : "#ddd",
                            }}
                          >
                            {delay !== null
                              ? formatMinutes(
                                  delay
                                )
                              : "--"}
                          </div>
                        </div>
                      </div>

                      {/* Traffic condition */}

                      {traffic && (
                        <div
                          style={{
                            marginTop: "8px",
                            fontSize: "11px",
                            color: trafficColor,
                          }}
                        >
                          <span
                            style={{
                              display:
                                "inline-block",
                              width: "7px",
                              height: "7px",
                              borderRadius: "50%",
                              background:
                                trafficColor,
                              boxShadow: `0 0 7px ${trafficColor}`,
                              marginRight: "6px",
                            }}
                          />

                          Traffic:{" "}
                          <strong>
                            {traffic}
                          </strong>
                        </div>
                      )}

                      {/* Reason */}

                      <div
                        style={{
                          color: "#8fa2b8",
                          fontSize: "10px",
                          marginTop: "7px",
                          lineHeight: "1.4",
                        }}
                      >
                        {getRouteReason(route)}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ----------------------------------------------------
              FALLBACK
          ----------------------------------------------------- */}

          {routeAlternatives.length === 0 && (
            <div
              style={{
                marginTop: "10px",
                padding: "14px",
                borderRadius: "9px",
                background:
                  "rgba(255,255,255,0.035)",
                border:
                  "1px solid rgba(255,255,255,0.08)",
                color: "#8fa2b8",
                fontSize: "12px",
                textAlign: "center",
              }}
            >
              Route alternatives are not available
              for this trip.
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}

/* ================================================================
   STYLES
================================================================ */

const labelStyle = {
  fontSize: "12px",
  color: "#9aabc0",
  display: "block",
  marginBottom: "5px",
};

const selectStyle = {
  width: "100%",
  padding: "9px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(255,255,255,0.15)",
  background: "#1c2938",
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
  background:
    "linear-gradient(135deg, #00bfff, #0080ff)",
  color: "#fff",
  fontSize: "13px",
  fontWeight: "bold",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const tripHeaderStyle = {
  background: "rgba(255,255,255,0.035)",
  border:
    "1px solid rgba(255,255,255,0.08)",
  borderRadius: "9px",
  padding: "10px 12px",
  marginBottom: "9px",
};

const summaryStyle = {
  background: "rgba(0,255,153,0.055)",
  border:
    "1px solid rgba(0,255,153,0.25)",
  borderRadius: "10px",
  padding: "12px",
  marginBottom: "9px",
  fontSize: "12px",
  color: "#ddd",
};

const bestDepartureStyle = {
  background:
    "linear-gradient(135deg, rgba(0,255,153,0.09), rgba(0,191,255,0.05))",
  border:
    "1px solid rgba(0,255,153,0.35)",
  borderRadius: "10px",
  padding: "12px 14px",
  marginBottom: "14px",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const sectionTitleStyle = {
  fontSize: "13px",
  color: "#dce5ef",
  marginBottom: "8px",
  fontWeight: "bold",
  display: "flex",
  alignItems: "center",
};

const bestBadgeStyle = {
  background: "#00ff99",
  color: "#001b11",
  padding: "3px 8px",
  borderRadius: "12px",
  fontSize: "9px",
  fontWeight: "bold",
};

const routeCardStyle = {
  borderRadius: "9px",
  padding: "10px 12px",
  fontSize: "12px",
};

const routeTypeStyle = {
  background: "rgba(255,255,255,0.09)",
  padding: "2px 6px",
  borderRadius: "4px",
  fontSize: "9px",
  color: "#9aabc0",
};

const metricStyle = {
  background: "rgba(0,0,0,0.15)",
  borderRadius: "6px",
  padding: "6px 7px",
};

const metricLabelStyle = {
  color: "#71849a",
  fontSize: "8px",
  fontWeight: "bold",
  marginBottom: "3px",
  display: "flex",
  alignItems: "center",
};

const metricValueStyle = {
  color: "#e8eef7",
  fontSize: "11px",
  fontWeight: "bold",
};

export default CommuteAdvisor;
