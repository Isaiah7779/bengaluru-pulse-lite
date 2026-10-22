// Firebase Authentication for the native app (Firebase JS SDK; same project and accounts
// as the web app). The web config values are public client identifiers, inlined per build
// from EXPO_PUBLIC_FIREBASE_*; access is enforced by Firebase Auth, the backend and the
// Firestore rules.
//
// The session is persisted in expo-secure-store (Android Keystore / iOS Keychain) rather
// than plain AsyncStorage. SecureStore keys allow only [A-Za-z0-9._-] and values are kept
// small, so keys are encoded and long values are split into chunks.
import { initializeApp, type FirebaseApp } from "firebase/app";
import { connectAuthEmulator, initializeAuth, type Auth } from "firebase/auth";
// getReactNativePersistence is only exported by the React Native build of @firebase/auth
// (Metro resolves its "react-native" export condition).
// @ts-expect-error -- not in the browser type definitions
import { getReactNativePersistence } from "@firebase/auth";
import * as SecureStore from "expo-secure-store";

const env = process.env;
const config = {
  apiKey: env.EXPO_PUBLIC_FIREBASE_API_KEY,
  authDomain: env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
  appId: env.EXPO_PUBLIC_FIREBASE_APP_ID,
};
const EMULATOR_HOST = env.EXPO_PUBLIC_FIREBASE_EMULATOR_HOST; // dev only, e.g. 192.168.1.7

export const firebaseEnabled = Boolean(config.apiKey && config.projectId && (config.appId || EMULATOR_HOST));
export const GOOGLE_WEB_CLIENT_ID = env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || "";

const CHUNK = 1800;
const safeKey = (key: string) => "fb_" + key.replace(/[^A-Za-z0-9._-]/g, (c) => `-${c.charCodeAt(0).toString(16)}-`);

export const secureStorage = {
  async getItem(key: string): Promise<string | null> {
    const k = safeKey(key);
    const count = await SecureStore.getItemAsync(`${k}.n`);
    if (count === null) return null;
    const parts: string[] = [];
    for (let i = 0; i < Number(count); i += 1) {
      const part = await SecureStore.getItemAsync(`${k}.${i}`);
      if (part === null) return null;
      parts.push(part);
    }
    return parts.join("");
  },
  async setItem(key: string, value: string): Promise<void> {
    const k = safeKey(key);
    await this.removeItem(key);
    const n = Math.max(1, Math.ceil(value.length / CHUNK));
    for (let i = 0; i < n; i += 1) await SecureStore.setItemAsync(`${k}.${i}`, value.slice(i * CHUNK, (i + 1) * CHUNK));
    await SecureStore.setItemAsync(`${k}.n`, String(n));
  },
  async removeItem(key: string): Promise<void> {
    const k = safeKey(key);
    const count = await SecureStore.getItemAsync(`${k}.n`);
    await SecureStore.deleteItemAsync(`${k}.n`);
    for (let i = 0; i < Number(count || 0); i += 1) await SecureStore.deleteItemAsync(`${k}.${i}`);
  },
};

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function firebaseAuth(): Auth {
  if (!firebaseEnabled) throw new Error("Firebase sign-in is not configured in this build.");
  if (!auth) {
    app = initializeApp(config);
    auth = initializeAuth(app, { persistence: getReactNativePersistence(secureStorage) });
    if (EMULATOR_HOST) connectAuthEmulator(auth, `http://${EMULATOR_HOST}:9099`, { disableWarnings: true });
  }
  return auth;
}

const MESSAGES: Record<string, string> = {
  "auth/invalid-credential": "Incorrect e-mail or password.",
  "auth/wrong-password": "Incorrect e-mail or password.",
  "auth/user-not-found": "Incorrect e-mail or password.",
  "auth/invalid-email": "Enter a valid e-mail address.",
  "auth/email-already-in-use": "An account with this e-mail already exists. Sign in instead.",
  "auth/weak-password": "Choose a stronger password.",
  "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
  "auth/network-request-failed": "Cannot reach the sign-in service. Check your connection.",
  "auth/account-exists-with-different-credential": "This e-mail already uses another sign-in method.",
  "auth/user-disabled": "This account has been disabled.",
};

export function authMessage(err: any): string {
  return MESSAGES[err?.code] || err?.message || "Something went wrong.";
}
