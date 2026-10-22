import { useEffect } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { BENGALURU_BOUNDS, BENGALURU_CENTER, CONGESTION_COLORS, ROUTE_COLORS, TILE_ATTRIBUTION, TILE_URL } from "../config";

const toLatLng = (coords) => coords.map(([lon, lat]) => [lat, lon]);
const routeColor = (r) => ROUTE_COLORS[(r.rank - 1) % ROUTE_COLORS.length];

function ClickPicker({ onPick }) {
  useMapEvents({
    click(e) {
      if (onPick) onPick({ lat: e.latlng.lat, lon: e.latlng.lng });
    },
  });
  return null;
}

function FitTo({ routes, selectedId, origin, destination }) {
  const map = useMap();
  useEffect(() => {
    const route = routes.find((r) => r.id === selectedId) || routes[0];
    if (route) {
      map.fitBounds(toLatLng(route.geometry.coordinates), { padding: [40, 40] });
    } else if (origin && destination) {
      map.fitBounds(
        [
          [origin.lat, origin.lon],
          [destination.lat, destination.lon],
        ],
        { padding: [60, 60] }
      );
    } else if (origin || destination) {
      const p = origin || destination;
      map.setView([p.lat, p.lon], 14);
    }
  }, [map, routes, selectedId, origin, destination]);
  return null;
}

export default function MapView({
  routes = [],
  selectedId,
  onSelect,
  origin,
  destination,
  picking,
  onPick,
  segments = [],
  incidents = [],
  shortcuts = [],
}) {
  const selected = routes.find((r) => r.id === selectedId);
  return (
    <MapContainer
      className={`map ${picking ? "picking" : ""}`}
      center={BENGALURU_CENTER}
      zoom={12}
      minZoom={10}
      maxBounds={[
        [12.4, 77.0],
        [13.6, 78.3],
      ]}
      bounds={BENGALURU_BOUNDS}
    >
      <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
      <ClickPicker onPick={picking ? onPick : null} />
      <FitTo routes={routes} selectedId={selectedId} origin={origin} destination={destination} />

      {segments.map((s) =>
        s.observation && s.geometry ? (
          <Polyline
            key={`seg-${s.segment_id}`}
            positions={toLatLng(s.geometry.coordinates)}
            pathOptions={{
              color: CONGESTION_COLORS[s.observation.congestion] || "#6b7280",
              weight: 5,
              opacity: s.status === "fresh" ? 0.85 : 0.35,
              dashArray: s.status === "fresh" ? null : "6 6",
            }}
          >
            <Tooltip sticky>
              {s.name}: {s.observation.congestion} · {s.observation.current_speed_kmph} km/h (
              {Math.round(s.observation.speed_ratio * 100)}% of free-flow) · {s.status}
            </Tooltip>
          </Polyline>
        ) : null
      )}

      {routes
        .filter((r) => r.id !== selectedId)
        .map((r) => (
          <Polyline
            key={r.id}
            positions={toLatLng(r.geometry.coordinates)}
            pathOptions={{ color: routeColor(r), weight: 5, opacity: 0.45 }}
            eventHandlers={{ click: () => onSelect && onSelect(r.id) }}
          >
            <Tooltip sticky>
              Route {r.id}: {Math.round(r.eta_s / 60)} min · {(r.distance_m / 1000).toFixed(1)} km
            </Tooltip>
          </Polyline>
        ))}
      {selected && (
        <>
          <Polyline positions={toLatLng(selected.geometry.coordinates)} pathOptions={{ color: "#ffffff", weight: 10, opacity: 0.9 }} />
          <Polyline positions={toLatLng(selected.geometry.coordinates)} pathOptions={{ color: routeColor(selected), weight: 6, opacity: 1 }} />
          {selected.incidents.map((i) => (
            <CircleMarker
              key={`ri-${i.id}`}
              center={[i.lat, i.lon]}
              radius={7}
              pathOptions={{ color: "#7f1d1d", fillColor: "#ef4444", fillOpacity: 0.9 }}
            >
              <Tooltip>
                {i.category.replace(/_/g, " ")}
                {i.road ? ` – ${i.road}` : ""} ({i.source})
              </Tooltip>
            </CircleMarker>
          ))}
        </>
      )}

      {incidents.map((i) => (
        <CircleMarker
          key={`inc-${i.id}`}
          center={[i.lat, i.lon]}
          radius={5}
          pathOptions={{ color: "#991b1b", fillColor: "#f87171", fillOpacity: 0.7, weight: 1 }}
        >
          <Tooltip>
            {i.category.replace(/_/g, " ")}
            {i.road_from ? ` – ${i.road_from}` : ""} ({i.source})
          </Tooltip>
        </CircleMarker>
      ))}

      {shortcuts.map((s) => (
        <Polyline key={`sc-${s.id}`} positions={toLatLng(s.geometry.coordinates)} pathOptions={{ color: "#0891b2", weight: 4, dashArray: "2 8" }}>
          <Tooltip sticky>
            Verified community {s.classification} ({s.confirmations} confirmations)
          </Tooltip>
        </Polyline>
      ))}

      {origin && (
        <CircleMarker center={[origin.lat, origin.lon]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#16a34a", fillOpacity: 1 }}>
          <Tooltip permanent direction="top" offset={[0, -8]}>
            A
          </Tooltip>
        </CircleMarker>
      )}
      {destination && (
        <CircleMarker center={[destination.lat, destination.lon]} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: "#dc2626", fillOpacity: 1 }}>
          <Tooltip permanent direction="top" offset={[0, -8]}>
            B
          </Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  );
}
