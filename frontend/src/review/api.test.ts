import { afterEach, expect, test, vi } from "vitest";
import { backendOrigin, cleanToken, loadConfig, postCorrection, postExplain, postHint, postSolve, saveConfig } from "./api";

afterEach(() => vi.unstubAllGlobals());

/** A backend that records what it was asked and answers with `body`. */
function backend(body: unknown, status = 200) {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });
  return fetch;
}
const config = { url: "https://back.example", token: "secret" };

test("whatever is pasted is reduced to the address of the server", () => {
  const origin = "https://some-words-here.trycloudflare.com";
  expect(backendOrigin(origin)).toBe(origin);
  expect(backendOrigin(`  ${origin}/  `)).toBe(origin);
  expect(backendOrigin(`${origin}/api/health`)).toBe(origin); // the link used to test the tunnel
  expect(backendOrigin("some-words-here.trycloudflare.com")).toBe(origin); // scheme left out
  expect(backendOrigin("http://localhost:8000/api/check")).toBe("http://localhost:8000");
  expect(backendOrigin("")).toBe("");
});

test("a token pasted with its .env label, quotes or spaces still works", () => {
  expect(cleanToken("  abc123  ")).toBe("abc123");
  expect(cleanToken("APP_TOKEN=abc123")).toBe("abc123");
  expect(cleanToken('APP_TOKEN = "abc123"')).toBe("abc123");
});

test("a correction posts the retyped step to its review", async () => {
  const fetch = backend({ id: "abc" });
  await postCorrection(config, "abc", "s3", "x = 3");
  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe("https://back.example/api/checks/abc/steps/s3");
  expect(init.method).toBe("POST");
  expect((init.body as FormData).get("latex")).toBe("x = 3");
  expect(init.headers).toEqual({ Authorization: "Bearer secret" });
});

test("a hint is asked for by review id", async () => {
  const fetch = backend({ id: "abc" });
  await postHint(config, "abc");
  expect(fetch.mock.calls[0][0]).toBe("https://back.example/api/checks/abc/hint");
  expect(fetch.mock.calls[0][1].method).toBe("POST");
});

test("the backend's own explanation reaches the panel", async () => {
  backend({ detail: "Se alcanzó el límite mensual de gasto." }, 402);
  await expect(postHint(config, "abc")).rejects.toThrow("límite mensual");
});

test("without connection nothing is sent", async () => {
  const fetch = backend({});
  vi.stubGlobal("navigator", { onLine: false });
  await expect(postCorrection(config, "abc", "s3", "x")).rejects.toThrow("Sin conexión");
  expect(fetch).not.toHaveBeenCalled();
});

test("the explanation and the solution are asked for by review id", async () => {
  const fetch = backend({ id: "abc" });
  await postExplain(config, "abc");
  await postSolve(config, "abc");
  expect(fetch.mock.calls.map((call) => call[0])).toEqual([
    "https://back.example/api/checks/abc/level/2",
    "https://back.example/api/checks/abc/solve",
  ]);
});

test("every request to the model carries the speed the user chose", async () => {
  const fetch = backend({ id: "abc" });
  const sent = () => (fetch.mock.calls.at(-1)![1].body as FormData).get("effort");

  await postHint({ ...config, speed: "fast" }, "abc"); // a request with no other body
  expect(sent()).toBe("low");
  await postCorrection({ ...config, speed: "balanced" }, "abc", "s3", "x = 3");
  expect(sent()).toBe("medium");
  expect((fetch.mock.calls.at(-1)![1].body as FormData).get("latex")).toBe("x = 3"); // alongside, not instead
  await postSolve(config, "abc"); // nothing chosen: as careful as before
  expect(sent()).toBe("high");
});

test("the speed setting is remembered, and an unknown one falls back to careful", () => {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
  expect(loadConfig().speed).toBe("careful");
  saveConfig({ ...config, speed: "fast" });
  expect(loadConfig()).toEqual({ ...config, speed: "fast" });
  store.set("paso:backend", JSON.stringify({ url: config.url, token: "t", speed: "warp" }));
  expect(loadConfig().speed).toBe("careful");
});
