import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

type StorageKind = "local" | "session";

type BrowserStorageStateOptions<T> = {
  storage: StorageKind;
  deserialize?(raw: string): T;
  serialize?(value: T): string;
  shouldRemove?(value: T): boolean;
};

function resolveStorage(kind: StorageKind): Storage | null {
  if (typeof window === "undefined") return null;
  return kind === "local" ? window.localStorage : window.sessionStorage;
}

export function useBrowserStorageState<T>(
  key: string,
  initialValue: T,
  {
    storage,
    deserialize = (raw) => JSON.parse(raw) as T,
    serialize = (value) => JSON.stringify(value),
    shouldRemove,
}: BrowserStorageStateOptions<T>,
): [T, Dispatch<SetStateAction<T>>] {
  const serializeRef = useRef(serialize);
  const shouldRemoveRef = useRef(shouldRemove);
  serializeRef.current = serialize;
  shouldRemoveRef.current = shouldRemove;

  const [value, setValue] = useState<T>(() => {
    try {
      const raw = resolveStorage(storage)?.getItem(key);
      return raw == null ? initialValue : deserialize(raw);
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      const store = resolveStorage(storage);
      if (!store) return;
      if (shouldRemoveRef.current?.(value)) {
        store.removeItem(key);
      } else {
        store.setItem(key, serializeRef.current(value));
      }
    } catch {
      // Storage may be unavailable in private mode or restricted webviews.
    }
  }, [key, storage, value]);

  return [value, setValue];
}
