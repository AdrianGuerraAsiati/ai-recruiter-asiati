import { describe, expect, it } from "vitest";

import { COUNTRY_OPTIONS, countryName } from "../data/countries";

describe("ASIATI operating countries", () => {
  it("only exposes commercial operating countries in selectors", () => {
    expect(COUNTRY_OPTIONS).toEqual([
      { code: "BR", name: "Brasil" },
      { code: "CL", name: "Chile" },
      { code: "CO", name: "Colombia" },
      { code: "EC", name: "Ecuador" },
    ]);
  });

  it("keeps labels for historical countries outside the selectable list", () => {
    expect(countryName("PE")).toBe("Perú");
    expect(countryName("CN")).toBe("China");
  });
});
