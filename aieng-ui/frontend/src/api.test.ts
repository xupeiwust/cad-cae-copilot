import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { api } from "./api";

function mockFetch(delayMs = 0, signal?: AbortSignal) {
  return new Promise<Response>((resolve, reject) => {
    if (signal?.aborted) {
      const err = new Error("Aborted");
      (err as Error & { name: string }).name = "AbortError";
      reject(err);
      return;
    }
    const timer = setTimeout(() => {
      resolve({
        ok: true,
        json: async () => ({ foo: "bar" }),
      } as Response);
    }, delayMs);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      const err = new Error("Aborted");
      (err as Error & { name: string }).name = "AbortError";
      reject(err);
    }, { once: true });
  });
}

describe("api request abort controller", () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.useRealTimers();
  });

  it("resolves on a successful JSON response", async () => {
    globalThis.fetch = vi.fn(() => mockFetch(0));
    const result = await api.getSettings();
    expect(result).toEqual({ foo: "bar" });
  });

  it("throws when the external signal is already aborted", async () => {
    globalThis.fetch = vi.fn(() => mockFetch(0));
    const controller = new AbortController();
    controller.abort();
    await expect(api.getSettings(controller.signal)).rejects.toThrow("Request aborted");
  });

  it("aborts an in-flight fetch when the external signal is aborted", async () => {
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => mockFetch(100_000, init?.signal));
    const controller = new AbortController();
    const promise = api.getSettings(controller.signal);
    await new Promise((r) => setTimeout(r, 10));
    controller.abort();
    await expect(promise).rejects.toThrow("Request aborted");
  });

  it("throws a timeout error when fetch is slow and no external signal is given", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => mockFetch(100_000, init?.signal));
    const promise = api.getSettings();
    vi.advanceTimersByTime(30_001);
    await expect(promise).rejects.toThrow("Request timed out after 30s");
  });

  it("throws 'Request aborted' instead of timeout when abort happens before timeout", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => mockFetch(100_000, init?.signal));
    const controller = new AbortController();
    const promise = api.getSettings(controller.signal);
    vi.advanceTimersByTime(100);
    controller.abort();
    vi.advanceTimersByTime(100);
    await expect(promise).rejects.toThrow("Request aborted");
    await expect(promise).rejects.not.toThrow("timed out");
  });

  it("passes a linked signal through to GET helpers", async () => {
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => mockFetch(100_000, init?.signal));
    const controller = new AbortController();
    const promise = api.getProject("proj-1", controller.signal);
    await new Promise((r) => setTimeout(r, 10));
    controller.abort();
    await expect(promise).rejects.toThrow("Request aborted");
  });

  it("passes a linked signal through to POST helpers", async () => {
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => mockFetch(100_000, init?.signal));
    const controller = new AbortController();
    const promise = api.createProject("test", controller.signal);
    await new Promise((r) => setTimeout(r, 10));
    controller.abort();
    await expect(promise).rejects.toThrow("Request aborted");
  });
});
