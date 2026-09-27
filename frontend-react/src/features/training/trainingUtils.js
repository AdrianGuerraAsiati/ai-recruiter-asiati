export function courseProgress(course) {
  return Number.isFinite(course?.progress_percent) ? course.progress_percent : 0;
}


export function isDirectVideo(url) {
  return /\.(mp4|webm|ogg)(\?|#|$)/i.test(String(url || ""));
}


export function googleDrivePreviewUrl(url) {
  const match = String(url || "").match(
    /^https:\/\/drive\.google\.com\/file\/d\/([^/]+)\//i,
  );
  return match
    ? `https://drive.google.com/file/d/${match[1]}/preview`
    : "";
}


export function lessonTypeLabel(type) {
  return {
    VIDEO: "Video",
    ARTICLE: "Lectura",
    RESOURCE: "Recurso",
    CHECKLIST: "Checklist",
  }[String(type || "VIDEO").toUpperCase()] || "Contenido";
}


export function lessonTypeIcon(type) {
  return {
    VIDEO: "▶",
    ARTICLE: "▤",
    RESOURCE: "↗",
    CHECKLIST: "✓",
  }[String(type || "VIDEO").toUpperCase()] || "•";
}


export function isTeamModule(module) {
  return String(module?.title || "").includes("Conoce al equipo");
}


export function isPortraitOnboardingModule(module) {
  return /^Módulo (?:[1-4]|6|7) ·/.test(String(module?.title || ""));
}


export function teamInitials(name) {
  return String(name || "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}


export function recommendedSession(lessons, nextLessonId) {
  const requiredPending = lessons.filter(
    (lesson) => !lesson.is_optional && !lesson.completed,
  );
  if (requiredPending.length === 0) {
    return { items: [], minutes: 0, hasUnknownDuration: false };
  }

  const startIndex = Math.max(
    0,
    requiredPending.findIndex((lesson) => lesson.id === nextLessonId),
  );
  const queue = requiredPending.slice(startIndex);
  const items = [];
  let minutes = 0;
  let hasUnknownDuration = false;

  for (const lesson of queue) {
    if (items.length >= 3) break;

    const lessonMinutes = Number(lesson.estimated_minutes);
    const hasKnownMinutes = Number.isFinite(lessonMinutes) && lessonMinutes > 0;

    if (items.length > 0 && hasKnownMinutes && minutes + lessonMinutes > 15) {
      break;
    }

    items.push(lesson);
    if (hasKnownMinutes) {
      minutes += lessonMinutes;
    } else {
      hasUnknownDuration = true;
      break;
    }
  }

  return { items, minutes, hasUnknownDuration };
}
