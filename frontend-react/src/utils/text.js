const ACRONYMS = new Set([
  "API", "APIS", "ASIATI", "AWS", "BI", "BPO", "CEO", "CFO", "COO", "CRM",
  "CTO", "ERP", "HR", "IA", "IT", "KAM", "QA", "SAP", "SQL", "TI", "UI",
  "UX", "LATAM",
]);

const LOWERCASE_WORDS = new Set([
  "a", "al", "con", "de", "del", "e", "el", "en", "la", "las", "los",
  "o", "para", "por", "sin", "u", "y",
]);

function capitalizePart(part, index) {
  if (!part) return part;
  const upper = part.toUpperCase();
  if (ACRONYMS.has(upper)) return upper;

  const lower = part.toLocaleLowerCase("es");
  if (index > 0 && LOWERCASE_WORDS.has(lower)) return lower;

  return lower.charAt(0).toLocaleUpperCase("es") + lower.slice(1);
}

export function titleCase(value) {
  const source = String(value || "").trim();
  if (!source) return "";

  let wordIndex = 0;
  return source
    .split(/(\s+|[–—])/)
    .map((token) => {
      if (!token || /^\s+$/.test(token) || token === "–" || token === "—") {
        return token;
      }

      const parts = token.split(/([/-])/);
      const rendered = parts.map((part) => {
        if (part === "/" || part === "-") return part;
        const suffixMatch = part.match(/^(.+?)(\([a-zA-Z]\))$/);
        if (suffixMatch) {
          const renderedBase = capitalizePart(suffixMatch[1], wordIndex);
          wordIndex += 1;
          return renderedBase + suffixMatch[2].toLocaleLowerCase("es");
        }
        const renderedPart = capitalizePart(part, wordIndex);
        wordIndex += 1;
        return renderedPart;
      });
      return rendered.join("");
    })
    .join("");
}
