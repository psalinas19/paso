import { expect, test } from "vitest";
import { parseBlocks, parseInline } from "./markdown";

test("inline text is split into prose, emphasis, code and maths", () => {
  expect(parseInline("Usa **la regla** de $x^2$ y `diff`, *no* otra.")).toEqual([
    { kind: "text", text: "Usa " },
    { kind: "bold", text: "la regla" },
    { kind: "text", text: " de " },
    { kind: "math", text: "x^2" },
    { kind: "text", text: " y " },
    { kind: "code", text: "diff" },
    { kind: "text", text: ", " },
    { kind: "italic", text: "no" },
    { kind: "text", text: " otra." },
  ]);
  // A product written with asterisks is not emphasis, and a lone dollar is not maths.
  expect(parseInline("2 * 3 * 4 cuesta $5")).toEqual([{ kind: "text", text: "2 * 3 * 4 cuesta $5" }]);
  // Markup is never interpreted: it stays text.
  expect(parseInline("<img onerror=alert(1)>")).toEqual([{ kind: "text", text: "<img onerror=alert(1)>" }]);
});

test("blocks: paragraphs, lists, headings and formulas on their own line", () => {
  const blocks = parseBlocks(["## Método", "Primero separa", "las variables.", "", "- uno", "- dos", "", "1. a", "2) b", "", "$$", "y = C e^{x}", "$$", "Listo. $$x=1$$"].join("\n"));
  expect(blocks).toEqual([
    { kind: "heading", text: "Método" },
    { kind: "paragraph", text: "Primero separa las variables." },
    { kind: "bullets", items: ["uno", "dos"] },
    { kind: "numbers", items: ["a", "b"] },
    { kind: "math", text: "y = C e^{x}" },
    { kind: "paragraph", text: "Listo. $$x=1$$" },
  ]);
  expect(parseBlocks("$$x^2$$")).toEqual([{ kind: "math", text: "x^2" }]);
  // An answer still being written, cut in the middle of a formula, does not break anything.
  expect(parseBlocks("Mira:\n$$\\frac{a}{")).toEqual([{ kind: "paragraph", text: "Mira:" }, { kind: "math", text: "\\frac{a}{" }]);
  expect(parseBlocks("")).toEqual([]);
});
