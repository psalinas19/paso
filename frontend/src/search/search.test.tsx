import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";
import { getCheck, searchReviews, type CheckResponse, type SearchHit } from "../review/api";
import { asReview, describeKinds, HitRow } from "./SearchView";

afterEach(() => vi.unstubAllGlobals());

const config = { url: "https://back.example", token: "secret" };
const hit: SearchHit = {
  check_id: "c1", subject: "ed", created_at: "2026-11-15T10:00:00Z", kinds: ["hint", "chat"],
  snippet: [{ text: "Revisa la ", hit: false }, { text: "división", hit: true }, { text: " del paso 3.", hit: false }],
};
const response: CheckResponse = {
  id: "c1",
  recognition: { steps: [{ id: "s1", latex: "x = 3", sympy: null, kind: "equation", relation: "given", derives_from: [], confidence: 1, legible: true, notes: null }], model: "m", warnings: [] },
  verification: { steps: [] },
  cost_usd: 0,
  usage: { month_spend_usd: 0.4, budget_usd: 20, checks_this_month: 3 },
};

test("a search is a GET with the words escaped, and costs nothing to ask", async () => {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify({ hits: [hit] })));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("navigator", { onLine: true });

  expect(await searchReviews(config, "¿raíz & signo?")).toEqual([hit]);
  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe("https://back.example/api/search?q=%C2%BFra%C3%ADz%20%26%20signo%3F");
  expect(init.method).toBeUndefined();
  expect(init.body).toBeUndefined();

  await getCheck(config, "c1");
  expect(fetch.mock.calls[1][0]).toBe("https://back.example/api/checks/c1");
});

test("where a hit was found reads as a sentence", () => {
  expect(describeKinds(["steps"])).toBe("tu desarrollo");
  expect(describeKinds(["hint", "chat"])).toBe("la pista y el chat");
  expect(describeKinds(["steps", "explanation", "solution"])).toBe("tu desarrollo, la explicación y la solución");
});

test("a result shows the passage with the matched words marked", () => {
  const html = renderToStaticMarkup(<HitRow hit={hit} onShow={() => {}} />);
  expect(html).toContain("<mark>división</mark>");
  expect(html.replace(/<[^>]+>/g, "")).toContain("en la pista y el chat");
  expect(html).toContain("Abrir la revisión");
});

test("a review from another device is shown read-only, without a made-up cost", () => {
  const html = renderToStaticMarkup(<HitRow hit={hit} onShow={() => {}} shown={asReview(response, hit.created_at)} />);
  const shown = html.replace(/<[^>]+>/g, " ");
  expect(shown).toContain("no está guardada en este iPad");
  expect(shown).toContain("Tu desarrollo");
  expect(shown).not.toContain("USD");
  expect(shown).not.toContain("Corregir lectura"); // nothing it could not do from here
  expect(html).not.toContain("Abrir la revisión");
});
