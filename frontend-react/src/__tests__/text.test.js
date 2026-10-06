import { describe, expect, it } from "vitest";

import { titleCase } from "../utils/text";

describe("titleCase", () => {
  it("normalizes all-caps vacancy titles while preserving business acronyms", () => {
    expect(titleCase("KAM – KEY ACCOUNT MANAGER CHILE"))
      .toBe("KAM – Key Account Manager Chile");
    expect(titleCase("COORDINADOR(A) ADMINISTRATIVO(A) Y DE OPERACIONES"))
      .toBe("Coordinador(a) Administrativo(a) y de Operaciones");
    expect(titleCase("ANALISTA DE IA Y AWS"))
      .toBe("Analista de IA y AWS");
  });
});
