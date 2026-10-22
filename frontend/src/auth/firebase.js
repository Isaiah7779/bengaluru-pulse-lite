// Firebase Web SDK, loaded lazily and only when the project is configured.
//
// The web config values are public client identifiers (they identify the project; access
// is controlled by Firebase Auth and the Firestore security rules), so CRA bakes them in at
// build time from REACT_APP_FIREBASE_*. Nothing secret belongs here.
//
// REACT_APP_FIREBASE_EMULATOR=true points Auth and Firestore at the local Emulator Suite
// (firebase/firebase.json: Auth 9099, Firestore 8085) for development and tests.
const env = process.env;

export const FIREBASE_CONFIG = {
  apiKey: env.REACT_APP_FIREBASE_API_KEY,
  authDomain: env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: env.REACT_APP_FIREBASE_PROJECT_ID,
  appId: env.REACT_APP_FIREBASE_APP_ID,
  storageBucket: env.REACT_APP_FIREBASE_STORAGE_BUCKET || undefined,
  messagingSenderId: env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID || undefined,
};

export const USE_EMULATOR = env.REACT_APP_FIREBASE_EMULATOR === "true";
const EMULATOR_HOST = env.REACT_APP_FIREBASE_EMULATOR_HOST || "127.0.0.1";

export const firebaseEnabled = Boolean(FIREBASE_CONFIG.apiKey && FIREBASE_CONFIG.projectId && (FIREBASE_CONFIG.appId || USE_EMULATOR));

let loading = null;

/** Resolves to { auth, db, A (firebase/auth), F (firebase/firestore) }. */
export function loadFirebase() {
  if (!firebaseEnabled) return Promise.reject(new Error("Firebase is not configured for this build"));
  if (!loading) {
    loading = Promise.all([import("firebase/app"), import("firebase/auth"), import("firebase/firestore")]).then(([appMod, A, F]) => {
      const app = appMod.initializeApp(FIREBASE_CONFIG);
      const auth = A.initializeAuth(app, {
        persistence: [A.indexedDBLocalPersistence, A.browserLocalPersistence, A.browserSessionPersistence],
        popupRedirectResolver: A.browserPopupRedirectResolver,
      });
      const db = F.getFirestore(app);
      if (USE_EMULATOR) {
        A.connectAuthEmulator(auth, `http://${EMULATOR_HOST}:9099`, { disableWarnings: true });
        F.connectFirestoreEmulator(db, EMULATOR_HOST, 8085);
      }
      return { app, auth, db, A, F };
    });
  }
  return loading;
}

const MESSAGES = {
  "auth/invalid-credential": "Incorrect e-mail or password.",
  "auth/wrong-password": "Incorrect e-mail or password.",
  "auth/user-not-found": "Incorrect e-mail or password.",
  "auth/invalid-email": "Enter a valid e-mail address.",
  "auth/email-already-in-use": "An account with this e-mail already exists. Sign in instead.",
  "auth/weak-password": "Choose a stronger password (at least 10 characters with upper- and lower-case letters and a digit).",
  "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
  "auth/network-request-failed": "Cannot reach the sign-in service. Check your connection.",
  "auth/popup-closed-by-user": "Google sign-in was closed before it finished.",
  "auth/cancelled-popup-request": "Google sign-in was closed before it finished.",
  "auth/unauthorized-domain": "Google sign-in is not enabled for this web address yet (add it under Firebase → Authentication → Authorized domains).",
  "auth/operation-not-allowed": "This sign-in method is not enabled for the project.",
  "auth/account-exists-with-different-credential": "This e-mail already uses another sign-in method. Sign in with that method first.",
  "auth/requires-recent-login": "For your security, sign in again and retry.",
  "auth/user-disabled": "This account has been disabled.",
};

/** Turn a Firebase error into a short, safe message. */
export function authMessage(err) {
  return MESSAGES[err?.code] || err?.message || "Something went wrong.";
}
