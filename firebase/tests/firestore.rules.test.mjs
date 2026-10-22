// Firestore security-rules tests, run against the local emulator:
//   npm run test:rules
import { after, before, beforeEach, describe, test } from "node:test";
import { readFileSync } from "node:fs";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { deleteDoc, doc, getDoc, getDocs, collection, serverTimestamp, setDoc, updateDoc } from "firebase/firestore";

let env;
const ALICE = "alice-uid";
const BOB = "bob-uid";

const verified = (uid) => env.authenticatedContext(uid, { email: `${uid}@pulse.example`, email_verified: true }).firestore();
const unverified = (uid) => env.authenticatedContext(uid, { email: `${uid}@pulse.example`, email_verified: false }).firestore();
const anonymous = () => env.unauthenticatedContext().firestore();

const favourite = (extra = {}) => ({
  label: "Home",
  detail: "Indiranagar",
  lat: 12.97,
  lon: 77.64,
  kind: "home",
  createdAt: serverTimestamp(),
  updatedAt: serverTimestamp(),
  ...extra,
});
const entry = (extra = {}) => ({ title: "Evening commute", body: "Slow at Silk Board.", mood: "stressful", createdAt: serverTimestamp(), updatedAt: serverTimestamp(), ...extra });

before(async () => {
  env = await initializeTestEnvironment({
    projectId: "demo-bengaluru-pulse",
    firestore: { rules: readFileSync(new URL("../firestore.rules", import.meta.url), "utf8"), host: "127.0.0.1", port: 8085 },
  });
});
beforeEach(async () => env.clearFirestore());
after(async () => env.cleanup());

describe("ownership", () => {
  test("owner can create, read, update and delete their favourite", async () => {
    const db = verified(ALICE);
    const ref = doc(db, `users/${ALICE}/favorites/f1`);
    await assertSucceeds(setDoc(ref, favourite()));
    await assertSucceeds(getDoc(ref));
    await assertSucceeds(updateDoc(ref, { label: "Home (new)", updatedAt: serverTimestamp() }));
    await assertSucceeds(deleteDoc(ref));
  });

  test("another user cannot read, list, write or delete", async () => {
    await assertSucceeds(setDoc(doc(verified(ALICE), `users/${ALICE}/journal/j1`), entry()));
    const bob = verified(BOB);
    await assertFails(getDoc(doc(bob, `users/${ALICE}/journal/j1`)));
    await assertFails(getDocs(collection(bob, `users/${ALICE}/journal`)));
    await assertFails(setDoc(doc(bob, `users/${ALICE}/journal/j2`), entry()));
    await assertFails(deleteDoc(doc(bob, `users/${ALICE}/journal/j1`)));
  });

  test("anonymous and unverified users are denied", async () => {
    await assertFails(getDoc(doc(anonymous(), `users/${ALICE}/favorites/f1`)));
    await assertFails(setDoc(doc(anonymous(), `users/${ALICE}/favorites/f1`), favourite()));
    await assertFails(setDoc(doc(unverified(ALICE), `users/${ALICE}/favorites/f1`), favourite()));
    await assertFails(getDocs(collection(unverified(ALICE), `users/${ALICE}/journal`)));
  });

  test("no profile document and no role field anywhere", async () => {
    const db = verified(ALICE);
    await assertFails(setDoc(doc(db, `users/${ALICE}`), { role: "admin" }));
    await assertFails(getDoc(doc(db, `users/${ALICE}`)));
    await assertFails(setDoc(doc(db, `users/${ALICE}/favorites/f1`), favourite({ role: "admin" })));
    await assertFails(setDoc(doc(db, `users/${ALICE}/preferences/app`), { vehicle: "car", isAdmin: true, updatedAt: serverTimestamp() }));
    await assertFails(setDoc(doc(db, `admins/${ALICE}`), { ok: true }));
    await assertFails(setDoc(doc(db, `users/${ALICE}/trips/t1`), { any: 1 }));
  });
});

describe("validation", () => {
  test("favourites: bounds, types and server timestamps", async () => {
    const db = verified(ALICE);
    await assertFails(setDoc(doc(db, `users/${ALICE}/favorites/a`), favourite({ lat: 28.6 }))); // outside Bengaluru
    await assertFails(setDoc(doc(db, `users/${ALICE}/favorites/b`), favourite({ label: "" })));
    await assertFails(setDoc(doc(db, `users/${ALICE}/favorites/c`), favourite({ lat: "12.9" })));
    await assertFails(setDoc(doc(db, `users/${ALICE}/favorites/d`), favourite({ kind: "secret" })));
    await assertFails(setDoc(doc(db, `users/${ALICE}/favorites/e`), favourite({ createdAt: new Date(0) })));
  });

  test("journal: size limits and immutable createdAt", async () => {
    const db = verified(ALICE);
    await assertFails(setDoc(doc(db, `users/${ALICE}/journal/a`), entry({ body: "x".repeat(5001) })));
    await assertFails(setDoc(doc(db, `users/${ALICE}/journal/b`), entry({ mood: "furious" })));
    await assertSucceeds(setDoc(doc(db, `users/${ALICE}/journal/c`), entry({ tripId: 42 })));
    await assertFails(updateDoc(doc(db, `users/${ALICE}/journal/c`), { createdAt: new Date(0), updatedAt: serverTimestamp() }));
    await assertSucceeds(updateDoc(doc(db, `users/${ALICE}/journal/c`), { body: "Edited", updatedAt: serverTimestamp() }));
  });

  test("preferences: single app document with known values", async () => {
    const db = verified(ALICE);
    await assertSucceeds(setDoc(doc(db, `users/${ALICE}/preferences/app`), { vehicle: "bicycle", routePreference: "balanced", avoid: "", departure: "now", updatedAt: serverTimestamp() }));
    await assertFails(setDoc(doc(db, `users/${ALICE}/preferences/other`), { vehicle: "car", updatedAt: serverTimestamp() }));
    await assertFails(setDoc(doc(db, `users/${ALICE}/preferences/app`), { vehicle: "plane", updatedAt: serverTimestamp() }));
  });
});
