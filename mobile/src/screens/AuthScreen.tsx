import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useAuth } from "../auth";
import { colors, ErrorBox } from "../ui";
import { ServerSettings } from "./AccountScreen";

function useRun() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  async function run<T>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const r = await fn();
      if (ok) setInfo(ok);
      return r;
    } catch (e: any) {
      setError(e.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, info, setInfo, run };
}

function Field(props: React.ComponentProps<typeof TextInput> & { label: string }) {
  return (
    <View>
      <Text style={styles.label}>{props.label}</Text>
      <TextInput style={styles.input} accessibilityLabel={props.label} placeholderTextColor={colors.muted} {...props} />
    </View>
  );
}

function SignInForm() {
  const auth = useAuth();
  const [view, setView] = useState<"signin" | "register" | "reset">("signin");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const { busy, error, info, run } = useRun();
  const firebase = auth.mode === "firebase";

  async function submit() {
    if (view === "reset") return run(() => auth.resetPassword(form.email), "If an account exists for that address, a reset link is on its way.");
    return run(() => (view === "register" ? auth.register(form.email, form.password, form.name) : auth.signIn(form.email, form.password)));
  }

  return (
    <View>
      <Text style={styles.eyebrow}>{view === "reset" ? "ACCOUNT RECOVERY" : view === "register" ? "JOIN BENGALURU PULSE" : "SIGN IN"}</Text>
      <Text style={styles.title}>{view === "reset" ? "Reset your password" : view === "register" ? "Create your account" : "Welcome back"}</Text>
      {view === "register" && <Field label="Your name" value={form.name} onChangeText={(name) => setForm({ ...form, name })} autoComplete="name" />}
      <Field label="E-mail" value={form.email} onChangeText={(email) => setForm({ ...form, email })} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
      {view !== "reset" && (
        <Field label="Password" value={form.password} onChangeText={(password) => setForm({ ...form, password })} secureTextEntry autoComplete={view === "register" ? "new-password" : "current-password"} />
      )}
      {view === "register" && <Text style={styles.muted}>At least 10 characters with upper- and lower-case letters and a digit.</Text>}
      <Pressable style={styles.primary} onPress={submit} disabled={busy} accessibilityRole="button">
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>{view === "reset" ? "Send reset link" : view === "register" ? "Create account" : "Sign in"}</Text>}
      </Pressable>
      {(error || (view === "signin" && auth.error)) && <ErrorBox text={(error || auth.error) as string} />}
      {info && <Text style={styles.info}>{info}</Text>}
      {auth.googleAvailable && view !== "reset" && (
        <Pressable style={styles.secondary} onPress={() => run(auth.signInWithGoogle)} disabled={busy} accessibilityRole="button">
          <Text style={styles.secondaryText}>Continue with Google</Text>
        </Pressable>
      )}
      <View style={styles.row}>
        {view === "signin" ? (
          <>
            <Pressable onPress={() => setView("register")}>
              <Text style={styles.link}>Create an account</Text>
            </Pressable>
            {firebase && (
              <Pressable onPress={() => setView("reset")}>
                <Text style={styles.link}>Forgot password?</Text>
              </Pressable>
            )}
          </>
        ) : (
          <Pressable onPress={() => setView("signin")}>
            <Text style={styles.link}>Back to sign in</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

function VerifyEmail() {
  const auth = useAuth();
  const { busy, error, info, setInfo, run } = useRun();
  return (
    <View>
      <Text style={styles.eyebrow}>ONE MORE STEP</Text>
      <Text style={styles.title}>Verify your e-mail</Text>
      <Text style={styles.body}>
        We sent a verification link to {auth.email}. Open it, then come back here. Bengaluru Pulse stays locked until the address is verified.
      </Text>
      <Pressable
        style={styles.primary}
        disabled={busy}
        onPress={async () => {
          const ok = await run(auth.refreshVerification);
          if (ok === false) setInfo("Not verified yet. Open the link in the e-mail, then try again.");
        }}
      >
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>I've verified — continue</Text>}
      </Pressable>
      <Pressable style={styles.secondary} disabled={busy} onPress={() => run(auth.resendVerification, "Verification e-mail sent again.")}>
        <Text style={styles.secondaryText}>Resend verification e-mail</Text>
      </Pressable>
      <Pressable onPress={auth.logout}>
        <Text style={styles.link}>Use a different account</Text>
      </Pressable>
      {error && <ErrorBox text={error} />}
      {info && <Text style={styles.info}>{info}</Text>}
    </View>
  );
}

function LinkAccount() {
  const auth = useAuth();
  const [form, setForm] = useState({ email: auth.email || "", password: "" });
  const { busy, error, run } = useRun();
  return (
    <View>
      <Text style={styles.eyebrow}>EXISTING ACCOUNT FOUND</Text>
      <Text style={styles.title}>Link your account</Text>
      <Text style={styles.body}>
        An earlier Bengaluru Pulse account uses {auth.email}. Enter that account's old password once to link it; its trips and role stay with it.
      </Text>
      <Field label="Old account e-mail" value={form.email} onChangeText={(email) => setForm({ ...form, email })} autoCapitalize="none" keyboardType="email-address" />
      <Field label="Old account password" value={form.password} onChangeText={(password) => setForm({ ...form, password })} secureTextEntry />
      <Pressable style={styles.primary} disabled={busy} onPress={() => run(() => auth.linkAccount(form.email, form.password))}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Link and continue</Text>}
      </Pressable>
      <Pressable onPress={auth.logout}>
        <Text style={styles.link}>Sign out</Text>
      </Pressable>
      {error && <ErrorBox text={error} />}
    </View>
  );
}

export default function AuthScreen() {
  const auth = useAuth();
  let body;
  if (auth.status === "loading") body = <ActivityIndicator style={{ marginVertical: 40 }} color={colors.accent} />;
  else if (auth.status === "unverified") body = <VerifyEmail />;
  else if (auth.status === "link") body = <LinkAccount />;
  else body = <SignInForm />;
  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <View style={styles.card}>{body}</View>
      {auth.status === "error" && (
        <Pressable style={styles.secondary} onPress={auth.reload}>
          <Text style={styles.secondaryText}>Try again</Text>
        </Pressable>
      )}
      <ServerSettings />
      <Text style={styles.fine}>Sign-in is handled by {auth.mode === "firebase" ? "Firebase Authentication" : "Bengaluru Pulse"}. Your session is kept in the device's secure storage.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 16, backgroundColor: colors.bg, flexGrow: 1 },
  card: { backgroundColor: colors.panel, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 16 },
  eyebrow: { fontSize: 11, letterSpacing: 1.6, color: colors.muted, fontWeight: "600" },
  title: { fontSize: 26, fontWeight: "700", color: colors.text, marginTop: 4, marginBottom: 10 },
  body: { color: colors.text, lineHeight: 20, marginBottom: 10 },
  label: { fontSize: 12, fontWeight: "600", color: colors.muted, marginTop: 8 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, minHeight: 48, fontSize: 16, marginTop: 4, backgroundColor: colors.panel, color: colors.text },
  primary: { backgroundColor: colors.text, borderRadius: 999, minHeight: 50, alignItems: "center", justifyContent: "center", marginTop: 14 },
  primaryText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  secondary: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, minHeight: 48, alignItems: "center", justifyContent: "center", marginTop: 10, backgroundColor: colors.panel },
  secondaryText: { color: colors.text, fontWeight: "600" },
  link: { color: colors.accent, paddingVertical: 10 },
  row: { flexDirection: "row", gap: 18, flexWrap: "wrap", marginTop: 4 },
  muted: { color: colors.muted, fontSize: 12, marginTop: 4 },
  info: { color: colors.accent, marginTop: 8 },
  fine: { color: colors.muted, fontSize: 12, marginTop: 16 },
});
