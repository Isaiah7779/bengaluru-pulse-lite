import * as Location from "expo-location";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api, BASIS_LABEL, fmtKm, fmtMin, Place, RouteResponse } from "../api";
import MapWebView from "../MapWebView";
import { Chip, colors, ErrorBox } from "../ui";

type Suggestion = { id: string; name: string; label: string; category_label: string; locality?: string; lat: number; lon: number };

function PlaceInput({ label, value, onChange, picking, onPick, near }: {
  label: string; value: Place | null; onChange: (p: Place) => void; picking: boolean; onPick: () => void; near: Place | null;
}) {
  const [text, setText] = useState(value?.label ?? "");
  const [items, setItems] = useState<Suggestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const typed = useRef(false);

  useEffect(() => { if (!typed.current) setText(value?.label ?? ""); }, [value]);
  useEffect(() => {
    if (!typed.current || text.trim().length < 2) { setItems([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await api<{ results: Suggestion[] }>("/v1/geocode/search", { params: { q: text.trim(), limit: 6, near_lat: near?.lat, near_lon: near?.lon } });
        setItems(r.results);
        setError(null);
      } catch (e: any) { setError(e.message); }
    }, 300);
    return () => clearTimeout(t);
  }, [text, near]);

  async function gps() {
    setBusy(true);
    setError(null);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") throw new Error("Location permission denied");
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const { latitude: lat, longitude: lon } = pos.coords;
      const rev = await api<{ label: string }>("/v1/geocode/reverse", { params: { lat, lon } }).catch(() => null);
      typed.current = false;
      onChange({ lat, lon, label: rev ? `My location (${rev.label})` : "My location" });
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <View style={{ marginBottom: 8 }}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.row}>
        <TextInput
          style={[styles.input, { flex: 1 }]}
          placeholder="Search a place or 12.97, 77.59"
          placeholderTextColor={colors.muted}
          value={text}
          onChangeText={(t) => { typed.current = true; setText(t); }}
          accessibilityLabel={`${label} search`}
        />
        <Pressable style={styles.iconBtn} onPress={gps} accessibilityLabel={`${label}: use my location`}>
          {busy ? <ActivityIndicator /> : <Text style={styles.iconText}>◎</Text>}
        </Pressable>
        <Pressable style={[styles.iconBtn, picking && styles.iconOn]} onPress={onPick} accessibilityLabel={`${label}: tap on map`}>
          <Text style={[styles.iconText, picking && { color: "#fff" }]}>⌖</Text>
        </Pressable>
      </View>
      {error && <Text style={styles.err}>{error}</Text>}
      {items.map((s) => (
        <Pressable key={s.id} style={styles.sugg} onPress={() => { typed.current = false; setItems([]); onChange({ lat: s.lat, lon: s.lon, label: s.name }); }}>
          <Text style={styles.suggName}>{s.name}</Text>
          <Text style={styles.muted}>{s.category_label}{s.locality ? ` · ${s.locality}` : ""}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const VEHICLES = [["car", "Car"], ["motorcycle", "Motorcycle"], ["bicycle", "Bicycle"], ["walk", "Walk"]] as const;
const PREFS = [["fastest", "Fastest"], ["shortest", "Shortest"], ["least_traffic_now", "Least traffic"], ["balanced", "Balanced"]] as const;
const DEPART = [["now", "Now", 0], ["30", "+30 min", 30], ["60", "+1 h", 60], ["120", "+2 h", 120]] as const;

export default function RouteScreen({ signedIn }: { signedIn: boolean }) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [picking, setPicking] = useState<"origin" | "destination" | null>(null);
  const [vehicle, setVehicle] = useState("car");
  const [pref, setPref] = useState("fastest");
  const [depart, setDepart] = useState("now");
  const [result, setResult] = useState<RouteResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onTap(p: { lat: number; lon: number }) {
    if (!picking) return;
    const target = picking;
    setPicking(null);
    const rev = await api<{ label: string }>("/v1/geocode/reverse", { params: p }).catch(() => null);
    const place = { ...p, label: rev?.label ?? `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}` };
    target === "origin" ? setOrigin(place) : setDestination(place);
  }

  async function plan() {
    if (!origin || !destination) { setError("Choose a start and a destination."); return; }
    setLoading(true);
    setError(null);
    try {
      const minutes = DEPART.find((d) => d[0] === depart)?.[2] ?? 0;
      const body: any = { origin, destination, vehicle, preference: pref, max_routes: 4, save_trip: signedIn };
      if (minutes) body.depart_at = new Date(Date.now() + minutes * 60000).toISOString();
      const r = await api<RouteResponse>("/v1/routes", { method: "POST", body });
      setResult(r);
      setSelected(r.recommended_route_id);
    } catch (e: any) { setResult(null); setError(e.message); } finally { setLoading(false); }
  }

  const route = result?.routes.find((r) => r.id === selected);
  return (
    <View style={{ flex: 1 }}>
      <View style={styles.mapBox}>
        <MapWebView routes={result?.routes ?? []} selectedId={selected} origin={origin} destination={destination} onTap={onTap} onSelect={setSelected} />
        {picking && <Text style={styles.banner}>Tap the map to set the {picking === "origin" ? "start" : "destination"}</Text>}
      </View>
      <ScrollView style={styles.panel} keyboardShouldPersistTaps="handled">
        <PlaceInput label="From" value={origin} onChange={(p) => { setOrigin(p); setResult(null); }} picking={picking === "origin"} onPick={() => setPicking(picking === "origin" ? null : "origin")} near={destination} />
        <PlaceInput label="To" value={destination} onChange={(p) => { setDestination(p); setResult(null); }} picking={picking === "destination"} onPick={() => setPicking(picking === "destination" ? null : "destination")} near={origin} />
        <View style={styles.chips}>{VEHICLES.map(([v, l]) => <Chip key={v} label={l} on={vehicle === v} onPress={() => setVehicle(v)} />)}</View>
        <View style={styles.chips}>{PREFS.map(([v, l]) => <Chip key={v} label={l} on={pref === v} onPress={() => setPref(v)} />)}</View>
        <View style={styles.chips}>{DEPART.map(([v, l]) => <Chip key={v} label={`Leave ${l}`} on={depart === v} onPress={() => setDepart(v)} />)}</View>
        <Pressable style={styles.primary} onPress={plan} disabled={loading} accessibilityRole="button">
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Find routes</Text>}
        </Pressable>
        {error && <ErrorBox text={error} />}
        {result && (
          <View>
            <Text style={styles.reco}>{result.recommendation}</Text>
            {result.preference_note && <Text style={styles.muted}>{result.preference_note}</Text>}
            <Text style={styles.muted}>Compared on: {BASIS_LABEL[result.comparison_basis]}</Text>
            {result.warnings.map((w, i) => <Text key={i} style={styles.warn}>{w}</Text>)}
            {result.routes.map((r) => (
              <Pressable key={r.id} onPress={() => setSelected(r.id)} style={[styles.card, r.id === selected && styles.cardOn]}>
                <Text style={styles.eta}>{fmtMin(r.eta_s)}  <Text style={styles.muted}>{fmtKm(r.distance_m)}</Text></Text>
                <Text style={styles.cardMeta}>
                  {r.recommended ? "Recommended · " : ""}{r.classification.type} · {BASIS_LABEL[r.eta_basis]}
                  {r.incidents.length ? ` · ${r.incidents.length} incident(s)` : ""}
                </Text>
                <Text numberOfLines={1} style={styles.muted}>{r.summary}</Text>
              </Pressable>
            ))}
            {route && (
              <View style={{ marginTop: 8 }}>
                <Text style={styles.h}>Why this route</Text>
                {route.explanation.map((l, i) => <Text key={i} style={styles.line}>• {l}</Text>)}
                <Text style={styles.h}>Steps</Text>
                {route.steps.slice(0, 40).map((s, i) => <Text key={i} style={styles.line}>{i + 1}. {s.instruction} ({fmtKm(s.distance_m)})</Text>)}
              </View>
            )}
            {result.weather && <Text style={styles.muted}>Weather: {result.weather.description}{result.weather.temperature_c != null ? `, ${Math.round(result.weather.temperature_c)}°C` : ""} — {result.weather.attribution}</Text>}
            <Text style={styles.h}>Data sources</Text>
            {result.data_sources.map((s) => <Text key={s.name} style={styles.muted}>{s.name}: {s.status} {s.detail ? `— ${s.detail}` : ""}</Text>)}
          </View>
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  mapBox: { height: "40%" },
  banner: { position: "absolute", top: 8, alignSelf: "center", backgroundColor: colors.accent, color: "#fff", padding: 8, borderRadius: 8, overflow: "hidden" },
  panel: { flex: 1, padding: 12, backgroundColor: colors.bg },
  label: { fontSize: 12, fontWeight: "700", color: colors.muted, marginBottom: 4 },
  row: { flexDirection: "row", gap: 6 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, height: 44, color: colors.text, backgroundColor: colors.panel },
  iconBtn: { width: 44, height: 44, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.panel },
  iconOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  iconText: { fontSize: 20, color: colors.text },
  sugg: { padding: 10, borderBottomWidth: 1, borderColor: colors.border, backgroundColor: colors.panel },
  suggName: { fontWeight: "600", color: colors.text },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginVertical: 4 },
  primary: { backgroundColor: colors.accent, borderRadius: 10, height: 46, alignItems: "center", justifyContent: "center", marginVertical: 8 },
  primaryText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  reco: { fontWeight: "700", color: colors.text, marginVertical: 6 },
  warn: { backgroundColor: colors.warnBg, color: colors.warnText, padding: 8, borderRadius: 8, marginVertical: 4 },
  card: { borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, marginVertical: 4, backgroundColor: colors.panel },
  cardOn: { borderColor: colors.accent, borderWidth: 2 },
  eta: { fontSize: 20, fontWeight: "700", color: colors.text },
  cardMeta: { color: colors.text, marginVertical: 2 },
  h: { fontWeight: "700", marginTop: 10, marginBottom: 4, color: colors.text },
  line: { color: colors.text, marginVertical: 2 },
  muted: { color: colors.muted },
  err: { color: colors.danger, marginTop: 4 },
});
