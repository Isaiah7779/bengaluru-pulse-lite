import { useEffect, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import type { Place, RouteOption } from "./api";

// Leaflet 1.9.4 from unpkg, pinned with Subresource Integrity hashes verified
// against the npm package. Tiles: OpenStreetMap (attribution shown).
const HTML = `<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>html,body,#m{height:100%;margin:0}</style></head><body><div id="m"></div><script>
var map = L.map('m', {zoomControl: true}).setView([12.9716, 77.5946], 12);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'}).addTo(map);
var layer = L.layerGroup().addTo(map);
var COLORS = ['#2563eb','#9333ea','#0d9488','#ea580c','#db2777'];
map.on('click', function(e){ window.ReactNativeWebView.postMessage(JSON.stringify({type:'tap', lat:e.latlng.lat, lon:e.latlng.lng})); });
window.render = function(state){
  layer.clearLayers(); var focus = null;
  (state.routes||[]).forEach(function(r){
    var ll = r.geometry.coordinates.map(function(c){return [c[1], c[0]];});
    var sel = r.id === state.selectedId;
    var line = L.polyline(ll, {color: COLORS[(r.rank-1)%COLORS.length], weight: sel?7:4, opacity: sel?1:0.45}).addTo(layer);
    line.on('click', function(){ window.ReactNativeWebView.postMessage(JSON.stringify({type:'select', id:r.id})); });
    if (sel) { focus = line; (r.incidents||[]).forEach(function(i){ L.circleMarker([i.lat,i.lon],{radius:6,color:'#7f1d1d',fillColor:'#ef4444',fillOpacity:0.9}).addTo(layer); }); }
  });
  if (state.origin) L.circleMarker([state.origin.lat,state.origin.lon],{radius:9,color:'#fff',weight:3,fillColor:'#16a34a',fillOpacity:1}).addTo(layer);
  if (state.destination) L.circleMarker([state.destination.lat,state.destination.lon],{radius:9,color:'#fff',weight:3,fillColor:'#dc2626',fillOpacity:1}).addTo(layer);
  if (focus) map.fitBounds(focus.getBounds(), {padding:[30,30]});
  else if (state.origin && state.destination) map.fitBounds([[state.origin.lat,state.origin.lon],[state.destination.lat,state.destination.lon]], {padding:[40,40]});
};
window.ReactNativeWebView.postMessage(JSON.stringify({type:'ready'}));
</script></body></html>`;

type Props = {
  routes: RouteOption[];
  selectedId?: string | null;
  origin?: Place | null;
  destination?: Place | null;
  onTap?: (p: { lat: number; lon: number }) => void;
  onSelect?: (id: string) => void;
};

export default function MapWebView({ routes, selectedId, origin, destination, onTap, onSelect }: Props) {
  // react-native-webview 14 types default P to `undefined`, making props `never` under TS 6;
  // an explicit `{}` type argument restores the real prop types.
  const ref = useRef<WebView<{}>>(null);
  const ready = useRef(false);
  const state = useMemo(
    () => JSON.stringify({ routes: routes.map((r) => ({ id: r.id, rank: r.rank, geometry: r.geometry, incidents: r.incidents })), selectedId, origin, destination }),
    [routes, selectedId, origin, destination]
  );

  useEffect(() => {
    if (ready.current) ref.current?.injectJavaScript(`window.render(${state}); true;`);
  }, [state]);

  function onMessage(e: WebViewMessageEvent) {
    const msg = JSON.parse(e.nativeEvent.data);
    if (msg.type === "ready") {
      ready.current = true;
      ref.current?.injectJavaScript(`window.render(${state}); true;`);
    } else if (msg.type === "tap") onTap?.({ lat: msg.lat, lon: msg.lon });
    else if (msg.type === "select") onSelect?.(msg.id);
  }

  return <WebView<{}> ref={ref} style={styles.map} originWhitelist={["*"]} source={{ html: HTML }} onMessage={onMessage} />;
}

const styles = StyleSheet.create({ map: { flex: 1 } });
