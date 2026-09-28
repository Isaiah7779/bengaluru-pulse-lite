import React, {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
  useMap,
} from "react-leaflet";

import L from "leaflet";
import "leaflet/dist/leaflet.css";


/*
|--------------------------------------------------------------------------
| DEFAULT BENGALURU VIEW
|--------------------------------------------------------------------------
*/

const BENGALURU_CENTER = [
  12.9716,
  77.5946,
];

const DEFAULT_ZOOM = 11;

/*
|--------------------------------------------------------------------------
| TRAFFIC COLORS
|--------------------------------------------------------------------------
*/

const TRAFFIC_COLORS = {
  LOW: "#00ff99",
  MODERATE: "#ffcc00",
  HIGH: "#ff8800",
  SEVERE: "#ff3333",
  UNKNOWN: "#888888",
};

/*
|--------------------------------------------------------------------------
| ROUTE COLORS
|--------------------------------------------------------------------------
*/

const PRIMARY_ROUTE_COLOR = "#00bfff";
const ALTERNATIVE_ROUTE_COLOR = "#bb66ff";

/*
|--------------------------------------------------------------------------
| NORMALIZE STATUS
|--------------------------------------------------------------------------
*/

const normalizeStatus = (status) => {
  if (!status) {
    return "UNKNOWN";
  }

  return String(status)
    .trim()
    .toUpperCase();
};

/*
|--------------------------------------------------------------------------
| GET TRAFFIC COLOR
|--------------------------------------------------------------------------
*/

const getTrafficColor = (status) => {
  return (
    TRAFFIC_COLORS[
      normalizeStatus(status)
    ] ||
    TRAFFIC_COLORS.UNKNOWN
  );
};

/*
|--------------------------------------------------------------------------
| CONVERT ROUTE GEOMETRY TO LAT/LON
|--------------------------------------------------------------------------
|
| OSRM GeoJSON:
|
| {
|   type: "LineString",
|   coordinates: [
|      [lon, lat],
|      [lon, lat]
|   ]
| }
|
|--------------------------------------------------------------------------
*/

const geometryToLatLngs = (
  geometry
) => {
  if (!geometry) {
    return [];
  }

  /*
  |--------------------------------------------------------------------------
  | GeoJSON Feature
  |--------------------------------------------------------------------------
  */

  if (
    geometry.type === "Feature" &&
    geometry.geometry
  ) {
    return geometryToLatLngs(
      geometry.geometry
    );
  }

  /*
  |--------------------------------------------------------------------------
  | GeoJSON LineString
  |--------------------------------------------------------------------------
  */

  if (
    geometry.type === "LineString" &&
    Array.isArray(
      geometry.coordinates
    )
  ) {
    return geometry.coordinates
      .filter(
        (coordinate) =>
          Array.isArray(
            coordinate
          ) &&
          coordinate.length >= 2
      )
      .map(
        (coordinate) => [
          Number(coordinate[1]),
          Number(coordinate[0]),
        ]
      )
      .filter(
        ([lat, lon]) =>
          Number.isFinite(lat) &&
          Number.isFinite(lon)
      );
  }

  /*
  |--------------------------------------------------------------------------
  | OSRM occasionally returns geometry
  | in another object wrapper.
  |--------------------------------------------------------------------------
  */

  if (
    geometry.coordinates &&
    Array.isArray(
      geometry.coordinates
    )
  ) {
    return geometry.coordinates
      .map(
        (coordinate) => [
          Number(coordinate[1]),
          Number(coordinate[0]),
        ]
      )
      .filter(
        ([lat, lon]) =>
          Number.isFinite(lat) &&
          Number.isFinite(lon)
      );
  }

  return [];
};

/*
|--------------------------------------------------------------------------
| ROUTE CAMERA CONTROLLER
|--------------------------------------------------------------------------
*/

function RouteCamera({
  routeResult,
}) {
  const map = useMap();

  useEffect(() => {
    /*
    |--------------------------------------------------------------------------
    | No route
    |--------------------------------------------------------------------------
    */

    if (
      !routeResult ||
      !routeResult.routes ||
      routeResult.routes.length === 0
    ) {
      return;
    }

    /*
    |--------------------------------------------------------------------------
    | Collect all route coordinates
    |--------------------------------------------------------------------------
    */

    const allPoints = [];

    routeResult.routes.forEach(
      (route) => {
        const points =
          geometryToLatLngs(
            route.geometry
          );

        points.forEach(
          (point) => {
            allPoints.push(point);
          }
        );
      }
    );

    /*
    |--------------------------------------------------------------------------
    | Nothing to fit
    |--------------------------------------------------------------------------
    */

    if (
      allPoints.length < 2
    ) {
      return;
    }

    /*
    |--------------------------------------------------------------------------
    | Fit map to route
    |--------------------------------------------------------------------------
    */

    const bounds =
      L.latLngBounds(
        allPoints
      );

    try {
      map.fitBounds(
        bounds,
        {
          padding: [
            45,
            45,
          ],

          maxZoom: 14,

          animate: true,

          duration: 0.8,
        }
      );
    } catch (error) {
      console.error(
        "Route camera error:",
        error
      );
    }
  }, [
    map,
    routeResult,
  ]);

  return null;
}

/*
|--------------------------------------------------------------------------
| ROUTE LOADING CAMERA
|--------------------------------------------------------------------------
*/

function RouteLoadingOverlay({
  loading,
}) {
  if (!loading) {
    return null;
  }

  return (
    <div
      style={{
        position: "absolute",
        top: "15px",
        left: "50%",
        transform:
          "translateX(-50%)",
        zIndex: 1000,

        padding:
          "10px 16px",

        borderRadius:
          "10px",

        background:
          "rgba(5,10,18,0.92)",

        border:
          "1px solid rgba(0,191,255,0.35)",

        color:
          "#00bfff",

        fontSize:
          "12px",

        fontWeight:
          "600",

        boxShadow:
          "0 4px 20px rgba(0,0,0,0.35)",

        pointerEvents:
          "none",
      }}
    >
      Calculating route...
    </div>
  );
}

/*
|--------------------------------------------------------------------------
| TRAFFIC LEGEND
|--------------------------------------------------------------------------
*/

function TrafficLegend() {
  return (
    <div
      style={{
        position:
          "absolute",

        bottom:
          "18px",

        left:
          "18px",

        zIndex:
          1000,

        padding:
          "12px 14px",

        borderRadius:
          "10px",

        background:
          "rgba(5,10,18,0.92)",

        border:
          "1px solid rgba(255,255,255,0.10)",

        boxShadow:
          "0 4px 18px rgba(0,0,0,0.35)",

        minWidth:
          "150px",
      }}
    >

      <div
        style={{
          color:
            "#fff",

          fontSize:
            "11px",

          fontWeight:
            "700",

          marginBottom:
            "8px",
        }}
      >
        TRAFFIC
      </div>

      {[
        [
          "LOW",
          "#00ff99",
        ],

        [
          "MODERATE",
          "#ffcc00",
        ],

        [
          "HIGH",
          "#ff8800",
        ],

        [
          "SEVERE",
          "#ff3333",
        ],
      ].map(
        ([label, color]) => (

          <div
            key={label}
            style={{
              display:
                "flex",

              alignItems:
                "center",

              gap:
                "7px",

              marginBottom:
                "5px",
            }}
          >

            <span
              style={{
                width:
                  "9px",

                height:
                  "9px",

                borderRadius:
                  "50%",

                background:
                  color,

                boxShadow:
                  `0 0 6px ${color}`,
              }}
            />

            <span
              style={{
                color:
                  "#aaa",

                fontSize:
                  "10px",
              }}
            >
              {label}
            </span>

          </div>

        )
      )}

    </div>
  );
}

/*
|--------------------------------------------------------------------------
| ROUTE LEGEND
|--------------------------------------------------------------------------
*/

function RouteLegend({
  routeResult,
}) {
  if (
    !routeResult ||
    !routeResult.routes ||
    routeResult.routes.length === 0
  ) {
    return null;
  }

  return (
    <div
      style={{
        position:
          "absolute",

        top:
          "18px",

        right:
          "18px",

        zIndex:
          1000,

        padding:
          "11px 13px",

        borderRadius:
          "10px",

        background:
          "rgba(5,10,18,0.92)",

        border:
          "1px solid rgba(255,255,255,0.10)",

        boxShadow:
          "0 4px 18px rgba(0,0,0,0.35)",
      }}
    >

      <div
        style={{
          color:
            "#fff",

          fontSize:
            "11px",

          fontWeight:
            "700",

          marginBottom:
            "8px",
        }}
      >
        ROUTES
      </div>

      <div
        style={{
          display:
            "flex",

          alignItems:
            "center",

          gap:
            "7px",

          marginBottom:
            "6px",
        }}
      >

        <span
          style={{
            width:
              "20px",

            height:
              "4px",

            borderRadius:
              "3px",

            background:
              PRIMARY_ROUTE_COLOR,
          }}
        />

        <span
          style={{
            color:
              "#aaa",

            fontSize:
              "10px",
          }}
        >
          Recommended
        </span>

      </div>

      {routeResult.routes.length >
        1 && (

        <div
          style={{
            display:
              "flex",

            alignItems:
              "center",

            gap:
              "7px",
          }}
        >

          <span
            style={{
              width:
                "20px",

              height:
                "3px",

              borderRadius:
                "3px",

              background:
                ALTERNATIVE_ROUTE_COLOR,

              opacity:
                0.8,
            }}
          />

          <span
            style={{
              color:
                "#aaa",

              fontSize:
                "10px",
            }}
          >
            Alternative
          </span>

        </div>

      )}

    </div>
  );
}

/*
|--------------------------------------------------------------------------
| MAIN COMPONENT
|--------------------------------------------------------------------------
*/

function TrafficMap({
  hotspots = [],
  selectedLocation,
  onLocationSelect,
  liveTraffic,
  liveTrafficLoading,
  routeResult,
  routeLoading,
}) {

  /*
  |--------------------------------------------------------------------------
  | Map reference
  |--------------------------------------------------------------------------
  */

  const mapRef =
    useRef(null);

  /*
  |--------------------------------------------------------------------------
  | TomTom layer reference
  |--------------------------------------------------------------------------
  */

  const trafficLayerRef =
    useRef(null);

  /*
  |--------------------------------------------------------------------------
  | Mounted state
  |--------------------------------------------------------------------------
  */

  const [
    mapReady,
    setMapReady,
  ] = useState(false);

  /*
  |--------------------------------------------------------------------------
  | Detect map initialization
  |--------------------------------------------------------------------------
  */

  const handleMapCreated =
    (map) => {
      mapRef.current =
        map;

      setMapReady(true);
    };

  /*
  |--------------------------------------------------------------------------
  | Render TomTom traffic
  |--------------------------------------------------------------------------
  |
  | Your backend's liveTraffic object can contain:
  |
  | traffic
  | roads
  | segments
  | data
  |
  | We handle common structures safely.
  |--------------------------------------------------------------------------
  */

  useEffect(() => {
    if (
      !mapReady ||
      !mapRef.current ||
      !liveTraffic
    ) {
      return;
    }

    /*
    |--------------------------------------------------------------------------
    | Remove previous traffic layer
    |--------------------------------------------------------------------------
    */

    if (
      trafficLayerRef.current
    ) {
      try {
        mapRef.current.removeLayer(
          trafficLayerRef.current
        );
      } catch (error) {
        console.warn(
          "Traffic layer cleanup failed:",
          error
        );
      }

      trafficLayerRef.current =
        null;
    }

    /*
    |--------------------------------------------------------------------------
    | Current TomTom data
    |--------------------------------------------------------------------------
    */

    const data =
      liveTraffic.traffic ||
      liveTraffic.roads ||
      liveTraffic.segments ||
      liveTraffic.data;

    /*
    |--------------------------------------------------------------------------
    | We only render point/segment data if
    | it is available in a supported format.
    |--------------------------------------------------------------------------
    */

    if (
      !Array.isArray(data)
    ) {
      return;
    }

    const group =
      L.layerGroup();

    let rendered =
      false;

    data.forEach(
      (item) => {

        /*
        |--------------------------------------------------------------------------
        | Coordinates
        |--------------------------------------------------------------------------
        */

        const lat =
          Number(
            item.lat ??
            item.latitude ??
            item.coordinates?.lat
          );

        const lon =
          Number(
            item.lon ??
            item.lng ??
            item.longitude ??
            item.coordinates?.lon
          );

        if (
          !Number.isFinite(lat) ||
          !Number.isFinite(lon)
        ) {
          return;
        }

        /*
        |--------------------------------------------------------------------------
        | Traffic status
        |--------------------------------------------------------------------------
        */

        const status =
          normalizeStatus(
            item.status ||
            item.traffic_status ||
            item.trafficStatus
          );

        const color =
          getTrafficColor(
            status
          );

        /*
        |--------------------------------------------------------------------------
        | Render traffic marker
        |--------------------------------------------------------------------------
        */

        const marker =
          L.circleMarker(
            [lat, lon],
            {
              radius:
                5,

              color,

              fillColor:
                color,

              fillOpacity:
                0.75,

              opacity:
                0.9,

              weight:
                1,
            }
          );

        /*
        |--------------------------------------------------------------------------
        | Popup
        |--------------------------------------------------------------------------
        */

        const roadName =
          item.road_name ||
          item.roadName ||
          item.name ||
          "Road";

        const speed =
          item.current_speed ??
          item.speed;

        const freeFlow =
          item.free_flow_speed ??
          item.freeFlowSpeed;

        marker.bindPopup(
          `
            <div style="min-width:180px">
              <strong>${roadName}</strong>
              <br/>
              <span>
                Traffic:
                ${status}
              </span>
              <br/>
              ${
                speed !==
                undefined
                  ? `Current speed:
                     ${speed} km/h<br/>`
                  : ""
              }
              ${
                freeFlow !==
                undefined
                  ? `Free-flow speed:
                     ${freeFlow} km/h`
                  : ""
              }
            </div>
          `
        );

        group.addLayer(
          marker
        );

        rendered =
          true;
      }
    );

    /*
    |--------------------------------------------------------------------------
    | Add traffic layer
    |--------------------------------------------------------------------------
    */

    if (rendered) {
      group.addTo(
        mapRef.current
      );

      trafficLayerRef.current =
        group;
    }

    /*
    |--------------------------------------------------------------------------
    | Cleanup
    |--------------------------------------------------------------------------
    */

    return () => {
      if (
        trafficLayerRef.current
      ) {
        try {
          mapRef.current?.removeLayer(
            trafficLayerRef.current
          );
        } catch (error) {
          console.warn(
            "Traffic cleanup error:",
            error
          );
        }

        trafficLayerRef.current =
          null;
      }
    };

  }, [
    liveTraffic,
    mapReady,
  ]);

  /*
  |--------------------------------------------------------------------------
  | Cleanup map on unmount
  |--------------------------------------------------------------------------
  */

  useEffect(() => {
    return () => {
      if (
        trafficLayerRef.current &&
        mapRef.current
      ) {
        try {
          mapRef.current.removeLayer(
            trafficLayerRef.current
          );
        } catch (error) {
          console.warn(
            "Map unmount cleanup:",
            error
          );
        }
      }
    };
  }, []);

  /*
  |--------------------------------------------------------------------------
  | Hotspot camera behavior
  |--------------------------------------------------------------------------
  |
  | IMPORTANT:
  |
  | When a route exists, hotspots must NOT call fitBounds.
  |
  | Otherwise the hotspot layer will continuously steal
  | the camera away from the selected route.
  |--------------------------------------------------------------------------
  */

  useEffect(() => {

    /*
    |--------------------------------------------------------------------------
    | Route owns camera
    |--------------------------------------------------------------------------
    */

    if (
      routeResult?.routes?.length >
      0
    ) {
      return;
    }

    /*
    |--------------------------------------------------------------------------
    | No map / no selected location
    |--------------------------------------------------------------------------
    */

    if (
      !mapReady ||
      !mapRef.current ||
      !selectedLocation
    ) {
      return;
    }

    /*
    |--------------------------------------------------------------------------
    | Find selected hotspot
    |--------------------------------------------------------------------------
    */

    const selected =
      hotspots.find(
        (item) =>
          item.location ===
          selectedLocation
      );

    if (!selected) {
      return;
    }

    const lat =
      Number(
        selected.lat ??
        selected.latitude
      );

    const lon =
      Number(
        selected.lon ??
        selected.lng ??
        selected.longitude
      );

    if (
      !Number.isFinite(lat) ||
      !Number.isFinite(lon)
    ) {
      return;
    }

    /*
    |--------------------------------------------------------------------------
    | Move camera only when no route exists
    |--------------------------------------------------------------------------
    */

    mapRef.current.flyTo(
      [lat, lon],
      13,
      {
        animate: true,
        duration: 0.8,
      }
    );

  }, [
    selectedLocation,
    hotspots,
    mapReady,
    routeResult,
  ]);

  /*
  |--------------------------------------------------------------------------
  | RENDER
  |--------------------------------------------------------------------------
  */

  return (
    <div
      style={{
        position:
          "relative",

        width:
          "100%",

        height:
          "100%",

        minHeight:
          "560px",

        borderRadius:
          "14px",

        overflow:
          "hidden",
      }}
    >

      {/* ============================================================
          MAP
      ============================================================ */}

      <MapContainer
        center={
          BENGALURU_CENTER
        }

        zoom={
          DEFAULT_ZOOM
        }

        scrollWheelZoom={
          true
        }

        style={{
          width:
            "100%",

          height:
            "100%",

          minHeight:
            "560px",

          background:
            "#081018",
        }}

        whenCreated={
          handleMapCreated
        }
      >

        {/* ==========================================================
            OSM BASE MAP
        ========================================================== */}

        <TileLayer
          attribution={
            '&copy; OpenStreetMap contributors'
          }

          url={
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          }

          maxZoom={
            19
          }
        />

        {/* ==========================================================
            ROUTE CAMERA
        ========================================================== */}

        <RouteCamera
          routeResult={
            routeResult
          }
        />

        {/* ==========================================================
            HOTSPOTS
        ========================================================== */}

        {hotspots.map(
          (spot, index) => {

            const lat =
              Number(
                spot.lat ??
                spot.latitude
              );

            const lon =
              Number(
                spot.lon ??
                spot.lng ??
                spot.longitude
              );

            if (
              !Number.isFinite(
                lat
              ) ||
              !Number.isFinite(
                lon
              )
            ) {
              return null;
            }

            const status =
              normalizeStatus(
                spot.status
              );

            const color =
              getTrafficColor(
                status
              );

            const congestion =
              Number(
                spot.congestion
              );

            return (

              <CircleMarker
                key={
                  spot.id ||
                  `${spot.location}-${index}`
                }

                center={[
                  lat,
                  lon,
                ]}

                radius={
                  selectedLocation ===
                  spot.location
                    ? 11
                    : 8
                }

                pathOptions={{
                  color,
                  fillColor:
                    color,

                  fillOpacity:
                    0.65,

                  weight:
                    selectedLocation ===
                    spot.location
                      ? 3
                      : 2,
                }}

                eventHandlers={{
                  click: () => {
                    if (
                      onLocationSelect
                    ) {
                      onLocationSelect(
                        spot.location
                      );
                    }
                  },
                }}
              >

                <Popup>

                  <div
                    style={{
                      minWidth:
                        "180px",
                    }}
                  >

                    <strong>
                      {spot.location}
                    </strong>

                    <br />

                    <span>
                      Congestion:
                      {" "}
                      {Number.isFinite(
                        congestion
                      )
                        ? congestion.toFixed(
                            1
                          )
                        : "--"}
                    </span>

                    <br />

                    <span
                      style={{
                        color,
                        fontWeight:
                          "700",
                      }}
                    >
                      {status}
                    </span>

                    {spot.is_peak_hour && (
                      <>
                        <br />
                        <span>
                          Peak hour
                        </span>
                      </>
                    )}

                  </div>

                </Popup>

              </CircleMarker>

            );
          }
        )}

        {/* ==========================================================
            ROUTES
        ========================================================== */}

        {routeResult?.routes?.map(
          (route, index) => {

            const points =
              geometryToLatLngs(
                route.geometry
              );

            if (
              points.length < 2
            ) {
              return null;
            }

            const recommended =
              route.recommended ===
              true;

            return (

              <Polyline
                key={
                  route.route_id ||
                  `route-${index}`
                }

                positions={
                  points
                }

                pathOptions={{
                  color:
                    recommended
                      ? PRIMARY_ROUTE_COLOR
                      : ALTERNATIVE_ROUTE_COLOR,

                  weight:
                    recommended
                      ? 7
                      : 5,

                  opacity:
                    recommended
                      ? 0.95
                      : 0.70,

                  dashArray:
                    recommended
                      ? undefined
                      : "10 8",

                  lineCap:
                    "round",

                  lineJoin:
                    "round",
                }}

              >

                <Popup>

                  <div
                    style={{
                      minWidth:
                        "200px",
                    }}
                  >

                    <strong>
                      Route {index + 1}
                    </strong>

                    {recommended && (
                      <>
                        {" "}
                        <span
                          style={{
                            color:
                              "#00bfff",
                          }}
                        >
                          — Recommended
                        </span>
                      </>
                    )}

                    <hr />

                    <div>
                      Distance:
                      {" "}
                      {Number(
                        route.distance_km ||
                        0
                      ).toFixed(
                        2
                      )}{" "}
                      km
                    </div>

                    <div>
                      Live ETA:
                      {" "}
                      {Number(
                        route.live_eta_min ||
                        route.duration_min ||
                        0
                      ).toFixed(
                        1
                      )}{" "}
                      min
                    </div>

                    <div>
                      Traffic delay:
                      {" "}
                      +
                      {Number(
                        route.traffic_delay_min ||
                        0
                      ).toFixed(
                        1
                      )}{" "}
                      min
                    </div>

                    <div>
                      Traffic:
                      {" "}
                      {route.traffic_status ||
                        "UNKNOWN"}
                    </div>

                  </div>

                </Popup>

              </Polyline>

            );
          }
        )}

      </MapContainer>

      {/* ============================================================
          LOADING
      ============================================================ */}

      <RouteLoadingOverlay
        loading={
          routeLoading
        }
      />

      {/* ============================================================
          TRAFFIC LEGEND
      ============================================================ */}

      <TrafficLegend />

      {/* ============================================================
          ROUTE LEGEND
      ============================================================ */}

      <RouteLegend
        routeResult={
          routeResult
        }
      />

      {/* ============================================================
          LIVE TRAFFIC STATUS
      ============================================================ */}

      <div
        style={{
          position:
            "absolute",

          bottom:
            "18px",

          right:
            "18px",

          zIndex:
            1000,

          padding:
            "7px 10px",

          borderRadius:
            "999px",

          background:
            "rgba(5,10,18,0.92)",

          border:
            "1px solid rgba(255,255,255,0.10)",

          color:
            liveTrafficLoading
              ? "#ffcc00"
              : "#00ff99",

          fontSize:
            "10px",

          fontWeight:
            "600",
        }}
      >

        <span>
          ●
        </span>

        {" "}

        {liveTrafficLoading
          ? "Updating live traffic..."
          : "Live traffic connected"}

      </div>

    </div>
  );
}

export default TrafficMap;