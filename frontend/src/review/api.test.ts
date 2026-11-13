import { afterEach, expect, test, vi } from "vitest";
import { backendOrigin, cleanToken, postCorrection, postHint } from "./api";

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
