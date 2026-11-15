import { expect, test } from "vitest";
import type { BankError } from "../review/api";
import { describeCounts, summariseBank } from "./summary";

const NOW = Date.parse("2026-11-15T12:00:00Z");
const DAY = 24 * 60 * 60 * 1000;
let next = 1;
const entry = (subject: string, type: string | null, daysAgo: number, resolved = false): BankError => ({
  id: next++, check_id: `c${next}`, step_id: "s3", subject: "ed", subject_name: subject, topic: null,
  error_type: type, error_label: type && { sign: "Error de signo", algebra: "Álgebra" }[type] || null,
  latex: "x = 4", detail: "No se sigue.", proved: true, resolved, created_at: new Date(NOW - daysAgo * DAY).toISOString(),
});

test("mistakes are counted per subject and type, pending apart from overcome", () => {
  const { subjects } = summariseBank(
    [entry("ED", "sign", 1), entry("ED", "sign", 2), entry("ED", "sign", 3, true), entry("ED", "algebra", 4), entry("Circuitos", null, 1)],
    NOW,
  );

  expect(subjects.map((s) => [s.name, s.open, s.resolved])).toEqual([["ED", 3, 1], ["Circuitos", 1, 0]]);
  expect(subjects[0].types).toEqual([
    { key: "sign", label: "Error de signo", open: 2, resolved: 1 },
    { key: "algebra", label: "Álgebra", open: 1, resolved: 0 },
  ]);
  expect(subjects[1].types).toEqual([{ key: "", label: "Sin clasificar", open: 1, resolved: 0 }]);
  // Newest first inside a subject.
  expect(subjects[0].entries.map((e) => Math.round((NOW - Date.parse(e.created_at)) / DAY))).toEqual([1, 2, 3, 4]);
});

test("the most frequent are those of the last month, classified, overcome or not", () => {
  const { frequent } = summariseBank(
    [
      entry("ED", "sign", 1), entry("ED", "sign", 29, true), entry("ED", "sign", 45), // the old one does not count
      entry("ED", "algebra", 3),
      entry("Circuitos", "sign", 2), // same type in another subject is its own line
      entry("ED", null, 1), entry("ED", null, 1), // unclassified says nothing about what to practise
    ],
    NOW,
  );

  expect(frequent).toEqual([
    { subject: "ED", label: "Error de signo", count: 2 },
    { subject: "ED", label: "Álgebra", count: 1 },
    { subject: "Circuitos", label: "Error de signo", count: 1 },
  ]);
});

test("a type the taxonomy no longer lists keeps its id as its name", () => {
  const gone = { ...entry("ED", "sign", 1), error_type: "retired", error_label: null };
  expect(summariseBank([gone], NOW).subjects[0].types[0].label).toBe("retired");
});

test("an empty bank is an empty summary", () => {
  expect(summariseBank([], NOW)).toEqual({ subjects: [], frequent: [] });
});

test("counts read naturally", () => {
  expect(describeCounts(1, 0)).toBe("1 pendiente");
  expect(describeCounts(3, 1)).toBe("3 pendientes · 1 superado");
  expect(describeCounts(0, 2)).toBe("0 pendientes · 2 superados");
});
