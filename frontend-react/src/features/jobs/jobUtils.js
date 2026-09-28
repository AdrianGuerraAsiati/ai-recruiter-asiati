export const MAX_PAGES = 100;
export const PAGE_SIZE_OPTIONS = [12, 24, 48];
export const SORT_OPTIONS = new Set([
  "created_desc",
  "created_asc",
  "candidates_desc",
  "candidates_asc",
]);

export function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value || ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function compactPageNumbers(totalPages, currentPage) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const pages = new Set([
    1,
    totalPages,
    currentPage - 1,
    currentPage,
    currentPage + 1,
  ]);
  return [...pages]
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((a, b) => a - b);
}

export function formatDate(iso) {
  if (!iso) return "Sin fecha";
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "Sin fecha";
    return date.toLocaleDateString("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "Sin fecha";
  }
}

export function indeedLifecycle(status) {
  return status?.status?.globalStatus?.lifecycleStatus
    || status?.status?.lifecycleStatus
    || null;
}

export function splitCandidateName(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  return {
    first_name: parts[0] || "",
    last_name: parts.slice(1).join(" "),
  };
}

export function todayInputValue(now = new Date()) {
  const local = new Date(now.getTime() - (now.getTimezoneOffset() * 60_000));
  return local.toISOString().slice(0, 10);
}

function proposalList(values) {
  return (Array.isArray(values) ? values : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function appendProposalSection(blocks, label, values) {
  const items = proposalList(values);
  if (!items.length) return;
  blocks.push(`${label}\n${items.map((item) => `- ${item}`).join("\n")}`);
}

export function formatEnrichmentProposalDescription(
  proposal,
  fallbackDescription = "",
) {
  const source = proposal || {};
  const blocks = [];
  const introduction = String(
    source.improved_description || fallbackDescription || "",
  ).trim();

  if (introduction) blocks.push(introduction);

  appendProposalSection(
    blocks,
    "Tecnologías requeridas",
    source.required_technologies,
  );
  appendProposalSection(
    blocks,
    "Tecnologías deseables",
    source.preferred_technologies,
  );

  appendProposalSection(
    blocks,
    "Certificaciones sugeridas",
    [
      ...proposalList(source.required_certifications),
      ...proposalList(source.preferred_certifications),
    ],
  );

  const experience = [];
  if (
    source.minimum_years_experience !== null
    && source.minimum_years_experience !== undefined
    && source.minimum_years_experience !== ""
  ) {
    experience.push(
      `Experiencia mínima de ${source.minimum_years_experience} años.`,
    );
  }
  experience.push(...proposalList(source.specific_experience));
  appendProposalSection(blocks, "Experiencia específica", experience);

  appendProposalSection(blocks, "Responsabilidades", source.responsibilities);
  appendProposalSection(blocks, "Conocimiento de dominio", source.domain_knowledge);
  appendProposalSection(blocks, "Educación", source.education);
  appendProposalSection(blocks, "Idiomas", source.languages);
  appendProposalSection(
    blocks,
    "Competencias técnicas",
    source.technical_competencies,
  );
  appendProposalSection(
    blocks,
    "Preguntas por validar (no son requisitos de evaluación)",
    source.assumptions_to_validate,
  );

  return blocks.join("\n\n").trim();
}
