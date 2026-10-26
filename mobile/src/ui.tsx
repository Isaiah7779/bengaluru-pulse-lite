import { Pressable, StyleSheet, Text } from "react-native";

export const colors = {
  bg: "#f6f7f9",
  panel: "#ffffff",
  text: "#111827",
  muted: "#6b7280",
  border: "#e5e7eb",
  accent: "#2563eb",
  danger: "#dc2626",
  warnBg: "#fff7ed",
  warnText: "#9a3412",
};

export function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.chip, on && styles.chipOn]} accessibilityRole="button" accessibilityState={{ selected: on }}>
      <Text style={[styles.chipText, on && { color: "#fff" }]}>{label}</Text>
    </Pressable>
  );
}

export function ErrorBox({ text }: { text: string }) {
  return <Text style={styles.error} accessibilityRole="alert">{text}</Text>;
}

const styles = StyleSheet.create({
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.panel },
  chipOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipText: { color: colors.text },
  error: { backgroundColor: "#fef2f2", color: "#991b1b", padding: 10, borderRadius: 8, marginVertical: 6 },
});
