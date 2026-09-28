import React from "react";

const VEHICLES = [
  { id: "car", label: "Car", icon: "🚗" },
  { id: "motorcycle", label: "Motorcycle", icon: "🏍️" },
  { id: "bicycle", label: "Bicycle", icon: "🚲" },
  { id: "walk", label: "Walk", icon: "🚶" },
];

function RoutePlanner({
  originText,
  destinationText,
  setOriginText,
  setDestinationText,
  vehicle,
  setVehicle,
  onCalculate,
  loading,
}) {
  return (
    <div
      style={{
        background: "#101b2d",
        border: "1px solid rgba(0,217,255,0.2)",
        borderRadius: "12px",
        padding: "18px",
        marginBottom: "16px",
      }}
    >
      <div
        style={{
          fontSize: "18px",
          fontWeight: "700",
          color: "#fff",
          marginBottom: "16px",
        }}
      >
        Route Planner
      </div>

      <div style={{ display: "grid", gap: "12px" }}>
        <div>
          <label
            style={{
              display: "block",
              color: "#8fa3b8",
              fontSize: "12px",
              marginBottom: "6px",
            }}
          >
            FROM
          </label>

          <input
            type="text"
            value={originText}
            onChange={(e) => setOriginText(e.target.value)}
            placeholder="Enter starting location"
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "12px",
              borderRadius: "8px",
              border: "1px solid rgba(255,255,255,0.12)",
              background: "#0b1424",
              color: "#fff",
              outline: "none",
            }}
          />
        </div>

        <div>
          <label
            style={{
              display: "block",
              color: "#8fa3b8",
              fontSize: "12px",
              marginBottom: "6px",
            }}
          >
            TO
          </label>

          <input
            type="text"
            value={destinationText}
            onChange={(e) => setDestinationText(e.target.value)}
            placeholder="Enter destination"
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "12px",
              borderRadius: "8px",
              border: "1px solid rgba(255,255,255,0.12)",
              background: "#0b1424",
              color: "#fff",
              outline: "none",
            }}
          />
        </div>

        <div>
          <label
            style={{
              display: "block",
              color: "#8fa3b8",
              fontSize: "12px",
              marginBottom: "8px",
            }}
          >
            VEHICLE
          </label>

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(4, minmax(0, 1fr))",
              gap: "8px",
            }}
          >
            {VEHICLES.map((item) => {
              const active = vehicle === item.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setVehicle(item.id)}
                  style={{
                    padding: "10px 6px",
                    borderRadius: "8px",
                    border: active
                      ? "1px solid #00d9ff"
                      : "1px solid rgba(255,255,255,0.1)",
                    background: active
                      ? "rgba(0,217,255,0.12)"
                      : "#0b1424",
                    color: active ? "#00d9ff" : "#c8d3df",
                    cursor: "pointer",
                    fontWeight: active ? "700" : "500",
                  }}
                >
                  <div>{item.icon}</div>
                  <div
                    style={{
                      fontSize: "11px",
                      marginTop: "4px",
                    }}
                  >
                    {item.label}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <button
          type="button"
          onClick={onCalculate}
          disabled={loading}
          style={{
            marginTop: "4px",
            padding: "12px",
            borderRadius: "8px",
            border: "1px solid #00d9ff",
            background: loading
              ? "#263445"
              : "#063344",
            color: "#00d9ff",
            cursor: loading
              ? "not-allowed"
              : "pointer",
            fontWeight: "700",
          }}
        >
          {loading ? "Calculating..." : "FIND ROUTES"}
        </button>
      </div>
    </div>
  );
}

export default RoutePlanner;