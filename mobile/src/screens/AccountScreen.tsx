import * as Location from "expo-location";
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api, apiBaseSource, apiBaseUrl, BASIS_LABEL, fmtKm, fmtMin, saveToken, setServerOverride } from "../api";
import { Chip, colors, ErrorBox } from "../ui";

type User = { id: number; email: string; display_name: string; role: string };

function ServerSettings() {
  const [current, setCurrent] = useState(apiBaseUrl());
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(value: string | null) {
    setBusy(true);
    setMsg(null);
    try {
      await setServerOverride(value);
      setCurrent(apiBaseUrl());
      setText("");
      setMsg(value ? "Connected and saved." : "Reset to the default for this build.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <View>
      <Text style={styles.h}>Server</Text>
      <Text style={styles.muted}>Using: {current || "not set"} ({apiBaseSource()})</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. https://<name>.trycloudflare.com"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        value={text}
        onChangeText={setText}
        accessibilityLabel="Server address"
      />
      <Pressable style={styles.secondary} onPress={() => save(text)} disabled={busy || !text.trim()}>
        <Text>{busy ? "Checking…" : "Test and save"}</Text>
      </Pressable>
      <Pressable onPress={() => save(null)}>
        <Text style={styles.link}>Use the default for this build</Text>
      </Pressable>
      {msg && <Text style={styles.line}>{msg}</Text>}
    </View>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    setError(null);
    try {
      const res = mode === "login"
        ? await api("/v1/auth/login", { method: "POST", body: { email, password } })
        : await api("/v1/auth/register", { method: "POST", body: { email, password, display_name: name } });
      await saveToken(res.access_token);
      onSignedIn(res.user);
    } catch (e: any) { setError(e.message); }
  }
  return (
    <View>
      <Text style={styles.h}>{mode === "login" ? "Sign in" : "Create account"}</Text>
      {mode === "register" && <TextInput style={styles.input} placeholder="Name" value={name} onChangeText={setName} />}
      <TextInput style={styles.input} placeholder="E-mail" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
      <TextInput style={styles.input} placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
      {error && <ErrorBox text={error} />}
      <Pressable style={styles.primary} onPress={submit}><Text style={styles.primaryText}>{mode === "login" ? "Sign in" : "Create account"}</Text></Pressable>
      <Pressable onPress={() => setMode(mode === "login" ? "register" : "login")}>
        <Text style={styles.link}>{mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}</Text>
      </Pressable>
    </View>
  );
}

function RecordTrip() {
  const [vehicle, setVehicle] = useState("car");
  const [points, setPoints] = useState<{ lat: number; lon: number; t: string; accuracy_m?: number | null }[]>([]);
  const [recording, setRecording] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sub = useRef<Location.LocationSubscription | null>(null);

  useEffect(() => () => sub.current?.remove(), []);

  async function toggle() {
    if (recording) { sub.current?.remove(); sub.current = null; setRecording(false); return; }
    setError(null);
    setResult(null);
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== "granted") { setError("Location permission denied"); return; }
    setPoints([]);
    sub.current = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.High, timeInterval: 5000, distanceInterval: 15 },
      (loc) => setPoints((p) => [...p, { lat: loc.coords.latitude, lon: loc.coords.longitude, t: new Date(loc.timestamp).toISOString(), accuracy_m: loc.coords.accuracy }])
    );
    setRecording(true);
  }

  async function submit() {
    try {
      const r = await api("/v1/community/submissions", { method: "POST", body: { vehicle, points } });
      setResult(r.status === "rejected" ? `Rejected: ${r.rejection_reason}` : r.candidate
        ? `Accepted — ${r.candidate.classification} candidate, ${r.candidate.confirmations}/${r.candidate.required_confirmations} independent confirmations (${r.candidate.state.replace("_", " ")})`
        : `Accepted — ${r.checks?.note ?? "no shortcut candidate"}`);
    } catch (e: any) { setError(e.message); }
  }

  return (
    <View>
      <Text style={styles.h}>Share a route you drove</Text>
      <Text style={styles.muted}>Verified only after map-matching, at least three independent confirmations and admin review.</Text>
      <View style={styles.chips}>{["car", "motorcycle", "bicycle", "walk"].map((v) => <Chip key={v} label={v} on={vehicle === v} onPress={() => setVehicle(v)} />)}</View>
      <Pressable style={[styles.primary, recording && { backgroundColor: colors.danger }]} onPress={toggle}>
        <Text style={styles.primaryText}>{recording ? `Stop (${points.length} points)` : "Record trip with GPS"}</Text>
      </Pressable>
      {!recording && points.length >= 10 && <Pressable style={styles.secondary} onPress={submit}><Text>Submit {points.length} points</Text></Pressable>}
      {result && <Text style={styles.line}>{result}</Text>}
      {error && <ErrorBox text={error} />}
    </View>
  );
}

function ReportIncident() {
  const [category, setCategory] = useState("flooding");
  const [description, setDescription] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  async function submit() {
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") throw new Error("Location permission denied");
      const pos = await Location.getCurrentPositionAsync({});
      const r = await api("/v1/incidents/report", { method: "POST", body: { category, description, lat: pos.coords.latitude, lon: pos.coords.longitude } });
      setMsg(r.message);
      setDescription("");
    } catch (e: any) { setMsg(e.message); }
  }
  return (
    <View>
      <Text style={styles.h}>Report an incident here</Text>
      <View style={styles.chips}>{["flooding", "accident", "road_closed", "road_works", "jam"].map((c) => <Chip key={c} label={c.replace("_", " ")} on={category === c} onPress={() => setCategory(c)} />)}</View>
      <TextInput style={styles.input} placeholder="What is happening?" value={description} onChangeText={setDescription} />
      <Pressable style={styles.secondary} onPress={submit}><Text>Send report (reviewed before publishing)</Text></Pressable>
      {msg && <Text style={styles.line}>{msg}</Text>}
    </View>
  );
}

export default function AccountScreen({ user, onUser }: { user: User | null; onUser: (u: User | null) => void }) {
  const [trips, setTrips] = useState<any[]>([]);
  useEffect(() => { if (user) api("/v1/me/trips").then(setTrips).catch(() => setTrips([])); }, [user]);
  if (!user)
    return (
      <ScrollView contentContainerStyle={styles.page}>
        <SignIn onSignedIn={onUser} />
        <ServerSettings />
      </ScrollView>
    );
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.h}>{user.display_name} <Text style={styles.muted}>({user.role})</Text></Text>
      <Pressable onPress={async () => { await api("/v1/auth/logout", { method: "POST" }).catch(() => null); await saveToken(null); onUser(null); }}>
        <Text style={styles.link}>Sign out</Text>
      </Pressable>
      <Text style={styles.h}>Trip history</Text>
      {trips.length ? trips.map((t) => (
        <Text key={t.id} style={styles.line}>
          {new Date(t.created_at).toLocaleString()} · {t.origin_label ?? "start"} → {t.destination_label ?? "destination"} · {fmtMin(t.chosen_route?.eta_s)} {fmtKm(t.chosen_route?.distance_m)} ({BASIS_LABEL[t.chosen_route?.eta_basis] ?? ""})
        </Text>
      )) : <Text style={styles.muted}>Trips you plan while signed in are saved here.</Text>}
      <RecordTrip />
      <ReportIncident />
      <ServerSettings />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 14, backgroundColor: colors.bg },
  h: { fontWeight: "700", fontSize: 16, marginTop: 14, marginBottom: 6, color: colors.text },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, height: 44, marginVertical: 4, backgroundColor: colors.panel, color: colors.text },
  primary: { backgroundColor: colors.accent, borderRadius: 10, height: 46, alignItems: "center", justifyContent: "center", marginVertical: 8 },
  primaryText: { color: "#fff", fontWeight: "700" },
  secondary: { borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 12, alignItems: "center", marginVertical: 6, backgroundColor: colors.panel },
  link: { color: colors.accent, marginVertical: 6 },
  muted: { color: colors.muted },
  line: { color: colors.text, marginVertical: 3 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginVertical: 6 },
});
