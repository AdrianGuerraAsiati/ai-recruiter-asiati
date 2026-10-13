import { describe, expect, it } from "vitest";
import { sentenceCaseLabel } from "../utils/text";

describe("display-only sentence case", () => {
  it("normalizes uppercase candidate names and job titles", () => {
    expect(sentenceCaseLabel("DEEJUD CHAFIK FAGER SAAVEDRA")).toBe("Deejud Chafik Fager Saavedra");
    expect(sentenceCaseLabel("ADMINISTRADOR DE PUNTO DE VENTA")).toBe("Administrador De Punto De Venta");
  });

  it("preserves accents and does not mutate the original value", () => {
    const raw = "  INGENIERÍA DE SISTEMAS ";
    expect(sentenceCaseLabel(raw)).toBe("Ingeniería De Sistemas");
    expect(raw).toBe("  INGENIERÍA DE SISTEMAS ");
    expect(sentenceCaseLabel(null)).toBe("");
  });
});
