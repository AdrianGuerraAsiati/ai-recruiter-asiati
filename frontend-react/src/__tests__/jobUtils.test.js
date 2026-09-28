import { describe, expect, it } from "vitest";

import {
  compactPageNumbers,
  formatDate,
  formatEnrichmentProposalDescription,
  indeedLifecycle,
  positiveInteger,
  splitCandidateName,
  todayInputValue,
} from "../features/jobs/jobUtils";

describe("jobUtils", () => {
  it("normalizes positive integers and pagination windows", () => {
    expect(positiveInteger("24", 12)).toBe(24);
    expect(positiveInteger("0", 12)).toBe(12);
    expect(positiveInteger("invalid", 12)).toBe(12);

    expect(compactPageNumbers(4, 2)).toEqual([1, 2, 3, 4]);
    expect(compactPageNumbers(12, 6)).toEqual([1, 5, 6, 7, 12]);
    expect(compactPageNumbers(12, 1)).toEqual([1, 2, 12]);
  });

  it("formats invalid dates defensively", () => {
    expect(formatDate(null)).toBe("Sin fecha");
    expect(formatDate("not-a-date")).toBe("Sin fecha");
  });

  it("reads Indeed lifecycle from both supported payload shapes", () => {
    expect(indeedLifecycle({
      status: { globalStatus: { lifecycleStatus: "OPEN" } },
    })).toBe("OPEN");
    expect(indeedLifecycle({
      status: { lifecycleStatus: "CLOSED" },
    })).toBe("CLOSED");
    expect(indeedLifecycle({})).toBeNull();
  });

  it("splits candidate names without losing compound surnames", () => {
    expect(splitCandidateName("Ana María Pérez Gómez")).toEqual({
      first_name: "Ana",
      last_name: "María Pérez Gómez",
    });
    expect(splitCandidateName("")).toEqual({
      first_name: "",
      last_name: "",
    });
  });

  it("builds the local date input value deterministically", () => {
    const fakeDate = {
      getTime: () => Date.UTC(2026, 8, 28, 15, 30, 0),
      getTimezoneOffset: () => 0,
    };
    expect(todayInputValue(fakeDate)).toBe("2026-09-28");
  });

  it("formats enrichment proposal sections and uses fallback description", () => {
    const formatted = formatEnrichmentProposalDescription(
      {
        required_technologies: ["Python", " FastAPI "],
        preferred_certifications: ["AWS"],
        minimum_years_experience: 3,
        specific_experience: ["APIs REST"],
        responsibilities: ["Diseñar servicios"],
        assumptions_to_validate: ["Disponibilidad híbrida"],
      },
      "Descripción base",
    );

    expect(formatted).toContain("Descripción base");
    expect(formatted).toContain("Tecnologías requeridas\n- Python\n- FastAPI");
    expect(formatted).toContain("Certificaciones sugeridas\n- AWS");
    expect(formatted).toContain("Experiencia mínima de 3 años.");
    expect(formatted).toContain("Preguntas por validar (no son requisitos de evaluación)");
  });
});
