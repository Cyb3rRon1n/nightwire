export type KeyValueStore = { getItem(key: string): string | null; setItem(key: string, value: string): void };

// Private windows, blocked site data and server rendering all make storage throw
// or vanish; the play screen must fall back to its defaults instead of crashing.
export function safeStore(get: () => KeyValueStore | undefined): KeyValueStore {
  return {
    getItem(key) {
      try { return get()?.getItem(key) ?? null; } catch { return null; }
    },
    setItem(key, value) {
      try { get()?.setItem(key, value); } catch { /* storage blocked: defaults stay */ }
    },
  };
}

export const browserStore = safeStore(() => window.localStorage);

export function readFlag(store: KeyValueStore, key: string, fallback: boolean): boolean {
  const value = store.getItem(key);
  return value === null ? fallback : value === "1";
}

export function writeFlag(store: KeyValueStore, key: string, value: boolean): void {
  store.setItem(key, value ? "1" : "0");
}
