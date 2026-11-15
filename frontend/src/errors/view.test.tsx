import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import type { BankError, Taxonomy } from "../review/api";
import { BankScreen, type BankStatus } from "./ErrorsView";

const taxonomy: Taxonomy[] = [{
  slug: "ed", name: "Ecuaciones Diferenciales", topics: ["edo-lineal"],
  error_types: [{ id: "sign", label: "Error de signo", description: "" }, { id: "algebra", label: "Álgebra", description: "" }],
}];
const entry = (id: number, more: Partial<BankError> = {}): BankError => ({
  id, check_id: "c1", step_id: "s3", subject: "ed", subject_name: "ED 2026-2", topic: "edo-lineal", error_type: "sign", error_label: "Error de signo",
  latex: "x = 4", detail: "No se sigue del paso anterior.", proved: true, resolved: false, created_at: new Date().toISOString(), ...more,
});
const actions = { onChange: async () => {}, onRemove: async () => {} };
const html = (entries: BankError[], status: BankStatus = { kind: "fresh" }, known = taxonomy) =>
  renderToStaticMarkup(<BankScreen entries={entries} taxonomy={known} status={status} actions={actions} onBack={() => {}} />);
const text = (...args: Parameters<typeof html>) => html(...args).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

test("the bank shows each subject with its counts, the frequent ones and every pending mistake", () => {
  const shown = text([entry(1), entry(2), entry(3, { error_type: "algebra", error_label: "Álgebra", proved: false })]);

  expect(shown).toContain("Mis errores");
  expect(shown).toContain("ED 2026-2 3 pendientes");
  expect(shown).toContain("Error de signo en ED 2026-2: 2 veces");
  expect(shown).toContain("Error comprobado con matemáticas");
  // What only the student vouches for is never passed off as proved.
  expect(shown).toContain("No se pudo comprobar: lo guardaste tú");
  expect(shown).toContain("No se sigue del paso anterior.");
  expect(shown.match(/Ya lo superé/g)).toHaveLength(3);
});

test("overcome mistakes are counted but put away until asked for", () => {
  const shown = text([entry(1), entry(2, { resolved: true, detail: "Otro detalle." })]);

  expect(shown).toContain("1 pendiente · 1 superado");
  expect(shown).toContain("Mostrar también los superados (1)");
  expect(shown).not.toContain("Otro detalle.");
  expect(text([entry(2, { resolved: true })])).toContain("Todo lo de esta materia está superado.");
});

test("the type can be picked from the subject's list, the topic from its suggestions", () => {
  const page = html([entry(1)]);
  expect(page).toContain('<option value="sign" selected="">Error de signo</option>');
  expect(page).toContain('<option value="algebra">Álgebra</option>');
  expect(page).toContain('<option value="edo-lineal"></option>');
  expect(page).toContain('value="edo-lineal"');
});

test("without the subject's list the type is shown but cannot be changed blind", () => {
  const page = html([entry(1)], { kind: "fresh" }, []);
  expect(page).not.toContain("<select");
  expect(page).toContain("<output>Error de signo</output>");
});

test("offline it says so, and an empty bank explains how to fill it", () => {
  const offline = text([entry(1)], { kind: "stale", why: "Sin conexión: esto necesita internet." });
  expect(offline).toContain("Sin conexión");
  expect(offline).toContain("lo último que se guardó en este iPad");

  const empty = text([]);
  expect(empty).toContain("Todavía no has guardado errores");
  expect(text([], { kind: "loading" })).not.toContain("Todavía no has guardado errores");
});

test("a subject with pending mistakes offers practice and shows its last round", () => {
  const round = {
    id: "r1", subject_name: "ED 2026-2", exam: false, created_at: Date.now(), notebook_id: "n", cost_usd: 0.03,
    exercises: (["passed", "pending", "pending"] as const).map((status, i) => ({
      id: `e${i}`, session_id: "r1", position: i, statement: "…", error_type: "sign", error_label: "Error de signo", topic: null,
      status, exam: false, check_id: null, answer_latex: null, page_id: `p${i}`,
    })),
  };
  const practise = { ...actions, onPractice: async () => {} };
  const render = (entries: BankError[]) =>
    renderToStaticMarkup(<BankScreen entries={entries} taxonomy={taxonomy} status={{ kind: "fresh" }} actions={practise} rounds={[round]} onBack={() => {}} onOpen={() => {}} />)
      .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

  const shown = render([entry(1)]);
  expect(shown).toContain("Repasar");
  expect(shown).toContain("1 de 3 sin errores, 2 por hacer");
  // Nothing pending: nothing to aim the exercises at.
  expect(render([entry(1, { resolved: true })])).not.toContain("Repasar");
  // Without a way to start one (the plain screen of the earlier tests) there is no button either.
  expect(text([entry(1)])).not.toContain("Repasar");
});
