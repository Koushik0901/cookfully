const DATABASE_NAME = "cookfully-offline";
const STORE_NAME = "responses";
const DATABASE_VERSION = 1;
const MAX_ENTRIES = 120;

type CachedResponse = {
  key: string;
  value: unknown;
  storedAt: number;
};

let databasePromise: Promise<IDBDatabase | null> | null = null;

function openDatabase(): Promise<IDBDatabase | null> {
  if (databasePromise) return databasePromise;
  if (typeof indexedDB === "undefined") return Promise.resolve(null);

  databasePromise = new Promise((resolve) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      const store = database.objectStoreNames.contains(STORE_NAME)
        ? request.transaction?.objectStore(STORE_NAME)
        : database.createObjectStore(STORE_NAME, { keyPath: "key" });
      if (store && !store.indexNames.contains("storedAt")) store.createIndex("storedAt", "storedAt");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });
  return databasePromise;
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Offline cache request failed."));
  });
}

export async function readOfflineResponse<T>(key: string): Promise<T | undefined> {
  const database = await openDatabase();
  if (!database) return undefined;
  try {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const value = await requestResult<CachedResponse | undefined>(transaction.objectStore(STORE_NAME).get(key));
    return value?.value as T | undefined;
  } catch {
    return undefined;
  }
}

export async function writeOfflineResponse(key: string, value: unknown): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put({ key, value, storedAt: Date.now() } satisfies CachedResponse);
    await new Promise<void>((resolve) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
    });
    await trimOfflineResponses(database);
  } catch {
    // Offline cache is an enhancement. A storage quota or private-browsing
    // restriction must never turn a successful API response into a failure.
  }
}

async function trimOfflineResponses(database: IDBDatabase): Promise<void> {
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const keys = await requestResult<IDBValidKey[]>(store.index("storedAt").getAllKeys());
    if (keys.length <= MAX_ENTRIES) return;
    for (const key of keys.slice(0, keys.length - MAX_ENTRIES)) store.delete(key);
  } catch {
    // Best effort only.
  }
}

export async function clearOfflineResponses(): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  try {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).clear();
  } catch {
    // Best effort only; sign-out still clears the in-memory query cache.
  }
}
