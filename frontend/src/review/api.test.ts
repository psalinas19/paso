import { expect, test } from "vitest";
import { backendOrigin, cleanToken } from "./api";

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
