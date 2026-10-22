import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Pressable, SafeAreaView, StyleSheet, Text, View } from "react-native";
import { api, loadServerOverride, loadToken } from "./src/api";
import AccountScreen from "./src/screens/AccountScreen";
import RouteScreen from "./src/screens/RouteScreen";
import TrafficScreen from "./src/screens/TrafficScreen";
import { colors } from "./src/ui";

type Tab = "route" | "traffic" | "account";

export default function App() {
  const [tab, setTab] = useState<Tab>("route");
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    loadServerOverride()
      .catch(() => null)
      .then(() => loadToken())
      .then((t) => (t ? api("/v1/auth/me").then(setUser) : null))
      .catch(() => setUser(null));
  }, []);

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.brand}>◉ Bengaluru Pulse</Text>
      </View>
      <View style={{ flex: 1 }}>
        {tab === "route" && <RouteScreen signedIn={!!user} />}
        {tab === "traffic" && <TrafficScreen />}
        {tab === "account" && <AccountScreen user={user} onUser={setUser} />}
      </View>
      <View style={styles.tabs} accessibilityRole="tablist">
        {(
          [
            ["route", "Navigate"],
            ["traffic", "Traffic"],
            ["account", user ? "Account" : "Sign in"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <Pressable key={key} style={styles.tab} onPress={() => setTab(key)} accessibilityRole="tab" accessibilityState={{ selected: tab === key }}>
            <Text style={[styles.tabText, tab === key && styles.tabOn]}>{label}</Text>
          </Pressable>
        ))}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: colors.panel },
  header: { paddingHorizontal: 16, paddingTop: 36, paddingBottom: 10, borderBottomWidth: 1, borderColor: colors.border },
  brand: { fontSize: 18, fontWeight: "700", color: colors.text },
  tabs: { flexDirection: "row", borderTopWidth: 1, borderColor: colors.border, backgroundColor: colors.panel },
  tab: { flex: 1, alignItems: "center", paddingVertical: 12 },
  tabText: { color: colors.muted, fontWeight: "600" },
  tabOn: { color: colors.accent },
});
