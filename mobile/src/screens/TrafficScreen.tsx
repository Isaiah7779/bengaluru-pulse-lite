import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { api, API_BASE_SOURCE, API_BASE_URL } from "../api";
import { colors, ErrorBox } from "../ui";

type Segment = {
  segment_id: number;
  name: string;
  status: string;
  observation: { congestion: string; current_speed_kmph: number; speed_ratio: number; age_minutes: number } | null;
};

const LEVEL_COLOR: Record<string, string> = { FREE: "#16a34a", MODERATE: "#ca8a04", HEAVY: "#ea580c", SEVERE: "#dc2626", CLOSED: "#7f1d1d" };

export default function TrafficScreen() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [note, setNote] = useState("");
  const [incidents, setIncidents] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [s, i] = await Promise.all([api("/v1/traffic/segments"), api("/v1/incidents", { params: { limit: 1 } })]);
      setSegments([...s.segments].sort((a: Segment, b: Segment) => (a.observation?.speed_ratio ?? 9) - (b.observation?.speed_ratio ?? 9)));
      setNote(s.coverage_note);
      setIncidents(i.total_active);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <FlatList
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: 12 }}
      data={segments}
      keyExtractor={(s) => String(s.segment_id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
      ListHeaderComponent={
        <View>
          {error && <ErrorBox text={error} />}
          <Text style={styles.muted}>Server: {API_BASE_URL} ({API_BASE_SOURCE})</Text>
          <Text style={styles.muted}>{note}</Text>
          <Text style={styles.stat}>{incidents ?? "–"} active incidents (TomTom)</Text>
        </View>
      }
      renderItem={({ item }) => (
        <View style={styles.row}>
          <View style={[styles.dot, { backgroundColor: item.observation ? LEVEL_COLOR[item.observation.congestion] : colors.border }]} />
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.muted}>
              {item.observation
                ? `${item.observation.congestion} · ${item.observation.current_speed_kmph} km/h · ${Math.round(item.observation.speed_ratio * 100)}% of free-flow · ${Math.round(item.observation.age_minutes)} min ago`
                : "no observation yet"}
              {item.status === "stale" ? " (stale)" : ""}
            </Text>
          </View>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderColor: colors.border },
  dot: { width: 14, height: 14, borderRadius: 7 },
  name: { fontWeight: "600", color: colors.text },
  muted: { color: colors.muted },
  stat: { fontWeight: "700", marginVertical: 8, color: colors.text },
});
