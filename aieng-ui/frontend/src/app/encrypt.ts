// AES raw keys must be 16/24/32 bytes. Keep this string at 32 ASCII bytes.
const KEY_DATA = new TextEncoder().encode("aieng-ui-local-enc-key-v1-32b!!");

async function getAesKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", KEY_DATA, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

export async function encryptText(plain: string): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    await getAesKey(),
    new TextEncoder().encode(plain),
  );
  const combined = new Uint8Array(iv.length + encrypted.byteLength);
  combined.set(iv);
  combined.set(new Uint8Array(encrypted), iv.length);
  return btoa(String.fromCharCode(...combined));
}

export async function decryptText(cipher: string): Promise<string> {
  const combined = Uint8Array.from(atob(cipher), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const data = combined.slice(12);
  const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, await getAesKey(), data);
  return new TextDecoder().decode(decrypted);
}
