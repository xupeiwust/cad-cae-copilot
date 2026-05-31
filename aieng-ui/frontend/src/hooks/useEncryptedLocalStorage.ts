import { useCallback, useEffect, useRef, useState } from "react";

import { decryptText, encryptText } from "../app/encrypt";

type UseEncryptedLocalStorageOptions = {
  shouldRemove?(value: string): boolean;
};

export function useEncryptedLocalStorage(
  key: string,
  initialValue: string,
  { shouldRemove }: UseEncryptedLocalStorageOptions = {},
): [string, (value: string) => void] {
  const shouldRemoveRef = useRef(shouldRemove);
  shouldRemoveRef.current = shouldRemove;

  const [value, setValue] = useState<string>(initialValue);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const raw = window.localStorage.getItem(key);
        if (raw && !cancelled) {
          const decrypted = await decryptText(raw);
          setValue(decrypted);
        }
      } catch {
        // Corrupt or missing entry — fall back to initial value.
      } finally {
        if (!cancelled) setHydrated(true);
      }
    })();
    return () => { cancelled = true; };
  }, [key]);

  const setStoredValue = useCallback(
    (next: string) => {
      setValue(next);
      void (async () => {
        try {
          if (shouldRemoveRef.current?.(next)) {
            window.localStorage.removeItem(key);
          } else {
            const encrypted = await encryptText(next);
            window.localStorage.setItem(key, encrypted);
          }
        } catch {
          // Storage may be unavailable in private mode.
        }
      })();
    },
    [key],
  );

  return [hydrated ? value : initialValue, setStoredValue];
}
