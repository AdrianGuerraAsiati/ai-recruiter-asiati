const COUNTRY_NAMES = {
  AR: "Argentina",
  BO: "Bolivia",
  BR: "Brasil",
  CL: "Chile",
  CO: "Colombia",
  CR: "Costa Rica",
  DO: "República Dominicana",
  EC: "Ecuador",
  SV: "El Salvador",
  GT: "Guatemala",
  HN: "Honduras",
  MX: "México",
  NI: "Nicaragua",
  PA: "Panamá",
  PY: "Paraguay",
  PE: "Perú",
  PR: "Puerto Rico",
  UY: "Uruguay",
  VE: "Venezuela",
  US: "Estados Unidos",
  ES: "España",
  CN: "China",
};

const ASIATI_COMMERCIAL_COUNTRY_CODES = ["BR", "CL", "CO", "EC"];

export const COUNTRY_OPTIONS = ASIATI_COMMERCIAL_COUNTRY_CODES.map((code) => ({
  code,
  name: COUNTRY_NAMES[code],
}));

export function countryName(code) {
  const normalized = String(code || "").trim().toUpperCase();
  return COUNTRY_NAMES[normalized] || normalized;
}

export function countryFlag(code) {
  const normalized = String(code || "").trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(normalized)) return "🌐";
  return String.fromCodePoint(
    ...[...normalized].map((char) => 127397 + char.charCodeAt(0)),
  );
}
