const DB_NAME = "talent-id-mobile-device";
const DB_VERSION = 1;
const STORE_NAME = "credentials";
const CURRENT_KEY = "current";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error || new Error("No se pudo abrir IndexedDB."));
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function withStore(mode, operation) {
  const db = await openDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const store = tx.objectStore(STORE_NAME);
      const request = operation(store);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("IndexedDB operation failed."));
    });
  } finally {
    db.close();
  }
}

function bytesToBase64Url(bytes) {
  let binary = "";
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return window.btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

export function mobileDeviceCryptoSupported() {
  return Boolean(
    window.crypto?.subtle
    && window.indexedDB
    && window.TextEncoder,
  );
}

export async function createMobileDeviceKey() {
  if (!mobileDeviceCryptoSupported()) {
    throw new Error("Este navegador no permite vincular el dispositivo de forma segura.");
  }

  const generated = await window.crypto.subtle.generateKey(
    {
      name: "ECDSA",
      namedCurve: "P-256",
    },
    true,
    ["sign", "verify"],
  );

  const publicKeyJwk = await window.crypto.subtle.exportKey(
    "jwk",
    generated.publicKey,
  );
  const privateJwk = await window.crypto.subtle.exportKey(
    "jwk",
    generated.privateKey,
  );
  const privateKey = await window.crypto.subtle.importKey(
    "jwk",
    privateJwk,
    {
      name: "ECDSA",
      namedCurve: "P-256",
    },
    false,
    ["sign"],
  );

  return {
    publicKeyJwk: {
      kty: publicKeyJwk.kty,
      crv: publicKeyJwk.crv,
      x: publicKeyJwk.x,
      y: publicKeyJwk.y,
      ext: true,
    },
    privateKey,
  };
}

export async function saveMobileDeviceCredential({ deviceId, label, privateKey }) {
  await withStore("readwrite", (store) => store.put({
    deviceId,
    label,
    privateKey,
  }, CURRENT_KEY));
}

export async function loadMobileDeviceCredential() {
  if (!mobileDeviceCryptoSupported()) return null;
  return withStore("readonly", (store) => store.get(CURRENT_KEY));
}

export async function clearMobileDeviceCredential() {
  if (!window.indexedDB) return;
  await withStore("readwrite", (store) => store.delete(CURRENT_KEY));
}

export async function signMobileDeviceChallenge(privateKey, message) {
  if (!privateKey) {
    throw new Error("No encontramos la llave privada de este dispositivo.");
  }
  const payload = new window.TextEncoder().encode(message);
  const signature = await window.crypto.subtle.sign(
    {
      name: "ECDSA",
      hash: "SHA-256",
    },
    privateKey,
    payload,
  );
  return bytesToBase64Url(new Uint8Array(signature));
}
