import { expect, test } from "vitest";
import { describeNotebookBackup, describeServerBackup } from "./describe";

test("the library says plainly whether the notes exist anywhere but on this iPad", () => {
  expect(describeNotebookBackup(false, 3)).toMatchObject({ tone: "warn" });
  expect(describeNotebookBackup(false, 0).text).toContain("solo en este iPad");
  expect(describeNotebookBackup(true, 0)).toEqual({ tone: "ok", text: "Todos tus cuadernos tienen copia en el servidor." });
  expect(describeNotebookBackup(true, 1).text).toBe("1 cuaderno tiene cambios sin copia en el servidor.");
  expect(describeNotebookBackup(true, 4)).toEqual({ tone: "warn", text: "4 cuadernos tienen cambios sin copia en el servidor." });
});

test("the server's own backup is described with what could go wrong said first", () => {
  const now = Date.parse("2026-11-15T12:00:00Z");
  const state = { enabled: true, offsite: true, ok: true, at: "2026-11-15T09:00:00Z", detail: "" };

  expect(describeServerBackup(state, now)).toBe("Último respaldo del servidor: hace 3 horas, con copia fuera del servidor.");
  // A backup that lives on the disk it protects is worth a warning, not a tick.
  expect(describeServerBackup({ ...state, offsite: false }, now)).toContain("SIN copia fuera del servidor");
  expect(describeServerBackup({ ...state, ok: false, detail: "rclone falló: sin permiso" }, now)).toBe(
    "El último respaldo del servidor FALLÓ (hace 3 horas): rclone falló: sin permiso",
  );
  expect(describeServerBackup({ ...state, at: "2026-11-11T12:00:00Z" }, now)).toContain("hace 4 días");
  expect(describeServerBackup({ ...state, at: "2026-11-15T11:50:00Z" }, now)).toContain("hace menos de una hora");
  expect(describeServerBackup({ ...state, at: null, ok: null }, now)).toBe("El servidor aún no hace su primer respaldo.");
  expect(describeServerBackup({ enabled: false, offsite: false, ok: null, at: null, detail: "" }, now)).toContain("no hace respaldos de sí mismo");
});
