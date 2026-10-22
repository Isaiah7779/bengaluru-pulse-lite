// Personal data in Cloud Firestore (favourites, journal, preferences), always under the
// signed-in user's own UID. The security rules (firebase/firestore.rules) enforce the same
// ownership, field and type checks server-side; nothing here is trusted on its own.
//
//   users/{uid}/favorites/{favoriteId}  { label, detail?, lat, lon, kind?, createdAt, updatedAt }
//   users/{uid}/journal/{entryId}       { title, body, mood?, tripId?, createdAt, updatedAt }
//   users/{uid}/preferences/app         { vehicle?, routePreference?, avoid?, departure?, updatedAt }
import { loadFirebase } from "../auth/firebase";

async function ctx() {
  const sdk = await loadFirebase();
  const uid = sdk.auth.currentUser?.uid;
  if (!uid) throw new Error("Sign in first.");
  return { ...sdk, uid };
}

const rows = (snap) => snap.docs.map((d) => ({ id: d.id, ...d.data() }));

export async function listFavorites() {
  const { db, F, uid } = await ctx();
  return rows(await F.getDocs(F.query(F.collection(db, "users", uid, "favorites"), F.orderBy("createdAt", "desc"), F.limit(50))));
}

export async function addFavorite({ label, detail, lat, lon, kind }) {
  const { db, F, uid } = await ctx();
  const data = { label: label.trim().slice(0, 120), lat: Number(lat), lon: Number(lon), createdAt: F.serverTimestamp(), updatedAt: F.serverTimestamp() };
  if (detail) data.detail = String(detail).slice(0, 200);
  if (kind) data.kind = kind;
  return F.addDoc(F.collection(db, "users", uid, "favorites"), data);
}

export async function removeFavorite(id) {
  const { db, F, uid } = await ctx();
  return F.deleteDoc(F.doc(db, "users", uid, "favorites", id));
}

export async function listJournal() {
  const { db, F, uid } = await ctx();
  return rows(await F.getDocs(F.query(F.collection(db, "users", uid, "journal"), F.orderBy("createdAt", "desc"), F.limit(100))));
}

export async function saveJournal({ id, title, body, mood, tripId }) {
  const { db, F, uid } = await ctx();
  const data = { title: title.trim().slice(0, 120), body: body.slice(0, 5000), updatedAt: F.serverTimestamp() };
  if (mood) data.mood = mood;
  data.tripId = tripId ? Number(tripId) : null;
  if (id) return F.updateDoc(F.doc(db, "users", uid, "journal", id), data);
  return F.addDoc(F.collection(db, "users", uid, "journal"), { ...data, createdAt: F.serverTimestamp() });
}

export async function removeJournal(id) {
  const { db, F, uid } = await ctx();
  return F.deleteDoc(F.doc(db, "users", uid, "journal", id));
}

export async function getPreferences() {
  const { db, F, uid } = await ctx();
  const snap = await F.getDoc(F.doc(db, "users", uid, "preferences", "app"));
  return snap.exists() ? snap.data() : null;
}

export async function savePreferences(prefs) {
  const { db, F, uid } = await ctx();
  const allowed = ["vehicle", "routePreference", "avoid", "departure"];
  const data = Object.fromEntries(Object.entries(prefs).filter(([k, v]) => allowed.includes(k) && v !== undefined));
  return F.setDoc(F.doc(db, "users", uid, "preferences", "app"), { ...data, updatedAt: F.serverTimestamp() });
}

/** Delete every personal Firestore document of the signed-in user. Returns the count. */
export async function deleteAllPersonalData() {
  const { db, F, uid } = await ctx();
  let count = 0;
  for (const name of ["favorites", "journal"]) {
    const snap = await F.getDocs(F.collection(db, "users", uid, name));
    for (const d of snap.docs) {
      await F.deleteDoc(d.ref);
      count += 1;
    }
  }
  const prefs = F.doc(db, "users", uid, "preferences", "app");
  if ((await F.getDoc(prefs)).exists()) {
    await F.deleteDoc(prefs);
    count += 1;
  }
  return count;
}
