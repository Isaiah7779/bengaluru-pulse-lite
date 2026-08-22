import React, { useEffect, useRef } from "react";

// Leaflet CSS must be imported in index.css or App.css
// We dynamically create markers based on congestion level

const CONGESTION_COLORS = {
  LOW: "#00ff99",
  MODERATE: "#ffcc00",
  HIGH: "#ff8800",
  SEVERE: "#ff3333",
};

const STATUS_EMOJI = {
  LOW: "🟢",
  MODERATE: "🟡",
  HIGH: "🟠",
  SEVERE: "🔴",
};

function TrafficMap({
  hotspots,
  selectedLocation,
  onLocationSelect,
  liveTraffic,
  liveTrafficLoading,
})  {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersRef = useRef([]);
  const liveRoadRef = useRef(null);

  useEffect(() => {
    // Dynamically import leaflet to avoid SSR issues
    if (mapInstanceRef.current) return;

    const L = window.L;
    if (!L) return;

    const map = L.map(mapRef.current, {
      center: [12.9716, 77.5946],
      zoom: 11,
      zoomControl: true,
      attributionControl: false,
    });

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution: "© OpenStreetMap © CARTO",
        subdomains: "abcd",
        maxZoom: 19,
      }
    ).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const L = window.L;
    if (!L || !mapInstanceRef.current || !hotspots.length) return;

    // Clear old markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    hotspots.forEach((spot) => {
      const color = CONGESTION_COLORS[spot.status] || "#aaaaaa";
      const isSelected = spot.location === selectedLocation;

      const pulseIcon = L.divIcon({
        className: "",
        html: `
          <div style="
            position: relative;
            width: ${isSelected ? 52 : 36}px;
            height: ${isSelected ? 52 : 36}px;
          ">
            <div style="
              position: absolute;
              top: 50%;
              left: 50%;
              transform: translate(-50%, -50%);
              width: ${isSelected ? 52 : 36}px;
              height: ${isSelected ? 52 : 36}px;
              border-radius: 50%;
              background: ${color};
              opacity: 0.25;
              animation: pulse 1.8s infinite;
            "></div>
            <div style="
              position: absolute;
              top: 50%;
              left: 50%;
              transform: translate(-50%, -50%);
              width: ${isSelected ? 28 : 20}px;
              height: ${isSelected ? 28 : 20}px;
              border-radius: 50%;
              background: ${color};
              border: ${isSelected ? "3px solid white" : "2px solid rgba(255,255,255,0.6)"};
              box-shadow: 0 0 ${isSelected ? 16 : 8}px ${color};
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 10px;
              font-weight: bold;
              color: #000;
            ">${spot.congestion.toFixed(0)}</div>
          </div>
        `,
        iconSize: [isSelected ? 52 : 36, isSelected ? 52 : 36],
        iconAnchor: [isSelected ? 26 : 18, isSelected ? 26 : 18],
      });

      const marker = L.marker([spot.lat, spot.lon], { icon: pulseIcon })
        .addTo(mapInstanceRef.current)
        .bindPopup(
          `<div style="background:#1a2535;color:white;padding:12px;border-radius:10px;min-width:200px;">
            <strong style="font-size:14px;">${STATUS_EMOJI[spot.status]} ${spot.location}</strong><br/>
            <span style="color:${color};font-size:20px;font-weight:bold;">${spot.congestion.toFixed(1)}</span>
            <span style="color:#aaa;"> / 30</span><br/>
            <span style="color:${color};">● ${spot.status}</span><br/>
            <small style="color:#ccc;">${spot.description}</small>
          </div>`,
          { className: "dark-popup" }
        )
        .on("click", () => {
          if (onLocationSelect) onLocationSelect(spot.location);
        });

      markersRef.current.push(marker);
    });
  }, [hotspots, selectedLocation, onLocationSelect]);

  // ------------------------------------------------------------
// TomTom live traffic road segment
// ------------------------------------------------------------

useEffect(() => {
  const L = window.L;

  if (!L || !mapInstanceRef.current) return;

  // Remove previous live road
  if (liveRoadRef.current) {
    liveRoadRef.current.remove();
    liveRoadRef.current = null;
  }

  if (
    !liveTraffic ||
    !liveTraffic.coordinates ||
    !liveTraffic.coordinates.coordinate
  ) {
    return;
  }

  const coordinates = liveTraffic.coordinates.coordinate;

  if (!coordinates.length) return;

  const roadPoints = coordinates.map((point) => [
    point.latitude,
    point.longitude,
  ]);

  // Determine road colour from live traffic condition
  let roadColor = "#00ff99";

  switch (liveTraffic.traffic_condition) {
    case "Moderate":
      roadColor = "#ffcc00";
      break;

    case "Heavy":
      roadColor = "#ff8800";
      break;

    case "Severe":
      roadColor = "#ff3333";
      break;

    default:
      roadColor = "#00ff99";
  }

  // Outer glow
  const roadGlow = L.polyline(roadPoints, {
    color: roadColor,
    weight: 12,
    opacity: 0.20,
    lineCap: "round",
    lineJoin: "round",
  }).addTo(mapInstanceRef.current);

  // Main traffic road
  const roadLine = L.polyline(roadPoints, {
    color: roadColor,
    weight: 6,
    opacity: 0.95,
    lineCap: "round",
    lineJoin: "round",
  }).addTo(mapInstanceRef.current);

  roadLine.bindPopup(`
    <div style="
      background:#1a2535;
      color:white;
      padding:14px;
      border-radius:10px;
      min-width:220px;
    ">
      <strong style="font-size:15px;">
        🚦 Live Traffic
      </strong>

      <br/><br/>

      <span style="color:${roadColor};font-size:18px;font-weight:bold;">
        ${liveTraffic.traffic_condition}
      </span>

      <br/>

      <span style="color:#ccc;">
        Current Speed:
      </span>
      ${liveTraffic.current_speed_kmph} km/h

      <br/>

      <span style="color:#ccc;">
        Free Flow:
      </span>
      ${liveTraffic.free_flow_speed_kmph} km/h

      <br/>

      <span style="color:#ccc;">
        Confidence:
      </span>
      ${liveTraffic.confidence}

      <br/><br/>

      <small style="color:#888;">
        Live data powered by TomTom
      </small>
    </div>
  `);

  // Keep glow and main line together
  liveRoadRef.current = L.layerGroup([
    roadGlow,
    roadLine,
  ]).addTo(mapInstanceRef.current);

  return () => {
    if (liveRoadRef.current) {
      liveRoadRef.current.remove();
      liveRoadRef.current = null;
    }
  };
}, [liveTraffic]);

  // Pan to selected location
  useEffect(() => {
    if (!mapInstanceRef.current || !hotspots.length) return;
    const spot = hotspots.find((h) => h.location === selectedLocation);
    if (spot) {
      mapInstanceRef.current.setView([spot.lat, spot.lon], 13, {
        animate: true,
        duration: 0.8,
      });
    }
  }, [selectedLocation, hotspots]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div
        ref={mapRef}
        style={{
          width: "100%",
          height: "100%",
          borderRadius: "16px",
          minHeight: "380px",
        }}
      />
      {/* Legend */}
      <div
        style={{
          position: "absolute",
          bottom: "16px",
          left: "16px",
          background: "rgba(10,20,35,0.9)",
          padding: "10px 14px",
          borderRadius: "10px",
          zIndex: 1000,
          fontSize: "12px",
          backdropFilter: "blur(8px)",
          border: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        {Object.entries(CONGESTION_COLORS).map(([status, color]) => (
          <div
            key={status}
            style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}
          >
            <div
              style={{
                width: "10px",
                height: "10px",
                borderRadius: "50%",
                background: color,
                boxShadow: `0 0 6px ${color}`,
              }}
            />
            <span style={{ color: "#ddd" }}>{status}</span>
          </div>
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0% { transform: translate(-50%, -50%) scale(1); opacity: 0.25; }
          50% { transform: translate(-50%, -50%) scale(1.6); opacity: 0; }
          100% { transform: translate(-50%, -50%) scale(1); opacity: 0.25; }
        }
        .dark-popup .leaflet-popup-content-wrapper {
          background: transparent !important;
          box-shadow: none !important;
          padding: 0 !important;
        }
        .dark-popup .leaflet-popup-tip {
          background: #1a2535 !important;
        }
      `}</style>
    </div>
  );
}

export default TrafficMap;
