// eslint-disable-next-line no-unused-vars
import React, { useRef, useState } from "react";
import "./onboarding-workspace.css";

import {
  EmptyState,
  LoadingState,
  ProgressBar,
} from "../../components/ui/StatePanel";
import TrainingEmployeeQuiz from "./TrainingEmployeeQuiz";
import {
  courseProgress,
  googleDrivePreviewUrl,
  isDirectVideo,
  isPortraitOnboardingModule,
  isTeamModule,
  lessonTypeIcon,
  lessonTypeLabel,
  teamInitials,
} from "./trainingUtils";

function TrackedTrainingVideo({ lesson, onVideoProgress }) {
  const videoRef = useRef(null);
  // Progress responses refresh the S3 signed URL. Replacing src on each refresh
  // makes the browser restart playback, even when the user only paused.
  // The component is keyed by lesson ID, so keep its first URL until that
  // lesson is left and remounted.
  const [playbackUrl] = useState(() => lesson.video_url);
  const restoredPositionRef = useRef(false);
  const segmentStartRef = useRef(null);
  const lastObservedTimeRef = useRef(null);
  const requestInFlightRef = useRef(false);
  const watchedPercent = Number(lesson?.video_progress?.watched_percent || 0);

  async function flushSegment(endTime) {
    const video = videoRef.current;
    const startTime = segmentStartRef.current;
    if (!video || startTime == null || requestInFlightRef.current) return;
    const end = Number(endTime);
    const start = Number(startTime);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start + 0.25) return;

    requestInFlightRef.current = true;
    segmentStartRef.current = end;
    try {
      await onVideoProgress(lesson, {
        duration_seconds: Number(video.duration || lesson.duration_seconds || 0),
        played_from_seconds: start,
        played_to_seconds: end,
        position_seconds: Number(video.currentTime || end),
      });
    } finally {
      requestInFlightRef.current = false;
    }
  }

  function handleLoadedMetadata(event) {
    if (restoredPositionRef.current) return;
    restoredPositionRef.current = true;

    const duration = Number(event.currentTarget.duration);
    const savedPosition = Number(lesson?.video_progress?.last_position_seconds || 0);
    // An ended video starts from the beginning when replayed. Restoring the
    // position only seeks the player; it does not count as watched time.
    if (Number.isFinite(duration) && duration > 0
      && Number.isFinite(savedPosition) && savedPosition > 0
      && savedPosition < duration - 1) {
      event.currentTarget.currentTime = savedPosition;
    }
  }

  function handlePlay(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    segmentStartRef.current = current;
    lastObservedTimeRef.current = current;
  }

  function handleTimeUpdate(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    const start = segmentStartRef.current;
    if (start == null) {
      segmentStartRef.current = current;
      lastObservedTimeRef.current = current;
      return;
    }
    if (!event.currentTarget.paused && current - start >= 5) {
      void flushSegment(current);
    }
    lastObservedTimeRef.current = current;
  }

  function handleSeeking() {
    const lastObserved = lastObservedTimeRef.current;
    if (lastObserved != null) {
      void flushSegment(lastObserved);
    }
    segmentStartRef.current = null;
    lastObservedTimeRef.current = null;
  }

  function handleSeeked(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    segmentStartRef.current = current;
    lastObservedTimeRef.current = current;
  }

  function handlePause(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    lastObservedTimeRef.current = current;
    void flushSegment(current);
  }

  function handleEnded(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    lastObservedTimeRef.current = current;
    void flushSegment(current);
  }

  const threshold = Number(lesson?.video_progress?.completion_threshold_percent || 80);

  return (
    <>
      <video
        ref={videoRef}
        key={lesson.id}
        controls
        preload="metadata"
        src={playbackUrl}
        aria-label={`Video: ${lesson.title}`}
        onLoadedMetadata={handleLoadedMetadata}
        onPlay={handlePlay}
        onTimeUpdate={handleTimeUpdate}
        onSeeking={handleSeeking}
        onSeeked={handleSeeked}
        onPause={handlePause}
        onEnded={handleEnded}
      >
        Tu navegador no puede reproducir este video.
      </video>
      <div className="training-video-watch-progress" aria-live="polite">
        <div>
          <strong>{Math.round(watchedPercent)}% reproducido</strong>
          <span>
            {lesson.completed
              ? "Video completado"
              : `Se completa automáticamente al reproducir al menos el ${threshold}%.`}
          </span>
        </div>
        <ProgressBar value={watchedPercent} />
      </div>
    </>
  );
}

export default function TrainingEmployeeJourney({
  canManage,
  myAssignments,
  selectedAssignmentId,
  setSelectedAssignmentId,
  detailLoading,
  employeeCourse,
  currentRecommendedSession,
  selectedAssignment,
  setActiveLessonId,
  activeLessonId,
  activeJourneyLesson,
  checklistSavingLessonId,
  updateChecklistItem,
  previousJourneyLesson,
  completeLesson,
  updateVideoProgress,
  saving,
  nextRequiredJourneyLesson,
  openFinalQuiz,
  employeeQuiz,
  quizAnswers,
  setQuizAnswers,
  quizResult,
  submitQuiz,
}) {
  const [focusMode, setFocusMode] = useState(false);
  const focusRef = useRef(null);
  const tabsRef = useRef(null);
  const modules = employeeCourse?.course?.modules || [];
  const isSingleCourse = myAssignments.length === 1;
  const activeModule = modules.find(
    (module) => module.id === activeJourneyLesson?.module?.id,
  ) || modules[0] || null;

  function moduleLabel(module) {
    return String(module?.title || "")
      .replace(/^Módulo\s+\d+\s*·\s*/i, "")
      .trim();
  }

  function selectLesson(id) {
    setActiveLessonId(id);
    focusRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function scrollModules(direction) {
    tabsRef.current?.scrollBy?.({ left: direction * 340, behavior: "smooth" });
  }

  function openModule(module) {
    const lessons = module?.lessons || [];
    const nextLesson = lessons.find(
      (lesson) => !lesson.completed && !lesson.is_optional,
    )
      || lessons.find((lesson) => !lesson.completed)
      || lessons[0];
    if (nextLesson) selectLesson(nextLesson.id);
  }

  return (
      <section className={`training-learning-section ${canManage ? "training-learning-after-admin" : ""}`}>
        <div className="training-section-heading">
          <div>
            <span className="eyebrow">Mi aprendizaje</span>
            <h2>Mis cursos</h2>
          </div>
          <span>{myAssignments.length} asignados</span>
        </div>

        {myAssignments.length === 0 ? (
          <section className="panel training-empty">
            <EmptyState
              compact
              icon="training"
              title="Aún no tienes cursos asignados"
              description="Cuando se publique una capacitación para tu perfil aparecerá aquí."
            />
          </section>
        ) : (
          <div className={`training-learning-layout ${isSingleCourse ? "is-single-course" : ""}`}>
            {!isSingleCourse && (
              <aside className="training-assignment-list">
                {myAssignments.map((assignment) => (
                <button
                  key={assignment.id}
                  type="button"
                  className={`training-assignment-card ${assignment.id === selectedAssignmentId ? "active" : ""}`}
                  onClick={() => setSelectedAssignmentId(assignment.id)}
                >
                  <div>
                    <span className="training-status training-status-published">
                      {assignment.status === "COMPLETED" ? "Completado" : "En curso"}
                    </span>
                    <h3>{assignment.course.title}</h3>
                    <p>{assignment.course.description || "Capacitación ASIATI"}</p>
                    {assignment.course.is_onboarding && (
                      <small className="training-onboarding-label">Inducción ASIATI</small>
                    )}
                  </div>
                  <div className="training-progress">
                    <span><strong>{courseProgress(assignment.course)}%</strong> completado</span>
                    <ProgressBar value={courseProgress(assignment.course)} />
                  </div>
                </button>
                ))}
              </aside>
            )}

            <section className="panel training-player-panel">
              {detailLoading && !employeeCourse ? (
                <LoadingState label="Cargando contenido…" compact />
              ) : employeeCourse?.course ? (
                <>
                  <header className="training-workspace-hero">
                    <div className="training-workspace-hero-content">
                      <span className="training-workspace-kicker">
                        {employeeCourse.course.is_onboarding ? "Tu inducción en ASIATI" : "Tu espacio de aprendizaje"}
                      </span>
                      <h2>{employeeCourse.course.title}</h2>
                      {employeeCourse.course.description && <p>{employeeCourse.course.description}</p>}
                      <div className="training-workspace-facts">
                        <span>{modules.length} módulos</span>
                        <span>{employeeCourse.course.completed_lessons} de {employeeCourse.course.lesson_count} actividades</span>
                        {employeeCourse.course.remaining_minutes > 0 && (
                          <span>~{employeeCourse.course.remaining_minutes} min pendientes</span>
                        )}
                      </div>
                    </div>
                    <div className="training-workspace-progress">
                      <div className="training-workspace-progress-label">
                        <span>Progreso general</span>
                        <strong>{Math.round(Number(employeeCourse.course.progress_percent || 0))}%</strong>
                      </div>
                      <ProgressBar value={employeeCourse.course.progress_percent} />
                      <small>Tu avance se guarda automáticamente.</small>
                    </div>
                  </header>

                  <section className="training-workspace-toolbar" aria-label="Continuar aprendizaje">
                    <div className="training-workspace-next">
                      <span>Siguiente paso</span>
                      <strong>
                        {currentRecommendedSession.items[0]?.title
                          || (employeeCourse.course.has_quiz && !selectedAssignment?.quiz_result?.passed
                            ? "Evaluación final"
                            : "Ruta de aprendizaje completada")}
                      </strong>
                      <small>
                        {currentRecommendedSession.items.length > 0
                          ? `${currentRecommendedSession.items.length} actividad${currentRecommendedSession.items.length === 1 ? "" : "es"} recomendada${currentRecommendedSession.items.length === 1 ? "" : "s"}`
                          : "Todas las actividades obligatorias están al día"}
                        {currentRecommendedSession.minutes > 0
                          ? ` · ~${currentRecommendedSession.minutes} min`
                          : ""}
                      </small>
                    </div>
                    <div className="training-workspace-actions">
                      {currentRecommendedSession.items.length > 0 ? (
                        <button className="btn btn-primary" type="button"
                          onClick={() => selectLesson(currentRecommendedSession.items[0].id)}>
                          Continuar aprendizaje <span aria-hidden="true">→</span>
                        </button>
                      ) : employeeCourse.course.has_quiz && !selectedAssignment?.quiz_result?.passed ? (
                        <button className="btn btn-primary" type="button" onClick={openFinalQuiz}>
                          Ir a evaluación final <span aria-hidden="true">→</span>
                        </button>
                      ) : (
                        <span className="training-workspace-finished">Ruta completada</span>
                      )}
                      <button type="button" className="training-focus-toggle"
                        aria-pressed={focusMode}
                        onClick={() => setFocusMode((current) => !current)}>
                        {focusMode ? "Mostrar actividades" : "Ampliar contenido"}
                      </button>
                    </div>
                  </section>

                  <div className="training-workspace-module-heading">
                    <div>
                      <h3>Explora los módulos</h3>
                      <p>Selecciona un módulo para ver sus actividades.</p>
                    </div>
                    <div className="training-workspace-module-controls">
                      <button type="button" aria-label="Ver módulos anteriores"
                        onClick={() => scrollModules(-1)}>←</button>
                      <button type="button" aria-label="Ver módulos siguientes"
                        onClick={() => scrollModules(1)}>→</button>
                    </div>
                  </div>

                  <nav
                    className="training-module-switcher-shell"
                    aria-label="Módulos del curso"
                  >
                    <div className="training-module-switcher" ref={tabsRef}>
                      {modules.map((module) => {
                        const isActive = activeModule?.id === module.id;
                        return (
                          <button
                            key={module.id}
                            type="button"
                            className={`training-module-tab ${isActive ? "active" : ""} ${module.is_complete ? "is-complete" : ""}`}
                            aria-current={isActive ? "step" : undefined}
                             title={module.title}
                            onClick={() => openModule(module)}
                            disabled={!module.lessons?.length}
                          >
                            <span>{module.is_complete ? "✓" : module.position}</span>
                            <div>
                              <small>Módulo {module.position}</small>
                              <strong>{moduleLabel(module)}</strong>
                            </div>
                            <b>{module.completed_lessons}/{module.lesson_count}</b>
                          </button>
                        );
                      })}
                    </div>
                  </nav>

                  <div className={`training-journey-layout ${isTeamModule(activeModule) ? "is-team-module" : ""} ${focusMode ? "is-expanded" : ""}`}>
                    <aside className="training-active-module-panel" aria-label="Contenido del módulo activo">
                      {activeModule ? (
                        <>
                          <div className="training-active-module-heading">
                            <span>Módulo {activeModule.position} de {modules.length}</span>
                            <strong>{moduleLabel(activeModule)}</strong>
                            <small>
                              {activeModule.completed_lessons}/{activeModule.lesson_count} completadas
                              {activeModule.has_unknown_duration
                                ? ` · ~${activeModule.estimated_minutes} min + contenido por confirmar`
                                : ` · ~${activeModule.estimated_minutes} min`}
                            </small>
                          </div>

                          <div className={`training-journey-lessons training-active-module-lessons ${isTeamModule(activeModule) ? "training-team-grid" : ""}`}>
                            {activeModule.lessons?.map((lesson) => (
                              <button
                                key={lesson.id}
                                type="button"
                                className={`training-journey-lesson-button ${isTeamModule(activeModule) ? "training-team-card" : ""} ${lesson.id === activeLessonId ? "active" : ""} ${lesson.completed ? "is-complete" : ""}`}
                                onClick={() => selectLesson(lesson.id)}
                              >
                                <span className={isTeamModule(activeModule) ? "training-team-avatar" : ""}>
                                  {lesson.completed
                                    ? "✓"
                                    : isTeamModule(activeModule)
                                      ? teamInitials(lesson.title)
                                      : lessonTypeIcon(lesson.content_type)}
                                </span>
                                <div>
                                  <strong>{lesson.title}</strong>
                                  <small>
                                    {isTeamModule(activeModule) ? "Video" : lessonTypeLabel(lesson.content_type)}
                                    {lesson.estimated_minutes
                                      ? ` · ~${lesson.estimated_minutes} min`
                                      : " · duración por confirmar"}
                                    {lesson.is_optional ? " · opcional" : ""}
                                  </small>
                                </div>
                              </button>
                            ))}
                          </div>

                          {employeeCourse.course.has_quiz && (
                            <button
                              type="button"
                              className={`training-journey-quiz-step ${selectedAssignment?.quiz_result?.passed ? "is-complete" : ""}`}
                              onClick={openFinalQuiz}
                            >
                              <span>{selectedAssignment?.quiz_result?.passed ? "✓" : "?"}</span>
                              <div>
                                <strong>Evaluación final</strong>
                                <small>
                                  {employeeCourse.course.completed_lessons < employeeCourse.course.lesson_count
                                    ? "Se habilita al completar la ruta"
                                    : selectedAssignment?.quiz_result?.passed
                                      ? "Aprobada"
                                      : "Lista para presentar"}
                                </small>
                              </div>
                            </button>
                          )}
                        </>
                      ) : (
                        <EmptyState
                          compact
                          icon="training"
                          title="Sin módulos"
                          description="Este curso todavía no tiene contenido disponible."
                        />
                      )}
                    </aside>

                    <article className="training-journey-focus" ref={focusRef}>
                      {activeJourneyLesson ? (
                        <>
                          <div className="training-journey-focus-meta">
                            <span>{activeJourneyLesson.module.title}</span>
                            <b>
                              {lessonTypeLabel(activeJourneyLesson.content_type)}
                              {activeJourneyLesson.estimated_minutes
                                ? ` · ~${activeJourneyLesson.estimated_minutes} min`
                                : " · duración por confirmar"}
                            </b>
                          </div>
                          <h3>{activeJourneyLesson.title}</h3>
                          {activeJourneyLesson.description && (
                            <p className="training-journey-description">{activeJourneyLesson.description}</p>
                          )}

                          {activeJourneyLesson.video_url && (
                            <div className={`training-video training-journey-video ${isPortraitOnboardingModule(activeJourneyLesson.module) ? "is-portrait" : ""}`}>
                              {isDirectVideo(activeJourneyLesson.video_url) ? (
                                <TrackedTrainingVideo
                                  key={activeJourneyLesson.id}
                                  lesson={activeJourneyLesson}
                                  onVideoProgress={updateVideoProgress}
                                />
                              ) : googleDrivePreviewUrl(activeJourneyLesson.video_url) ? (
                                <>
                                  <iframe
                                    className="training-drive-player"
                                    src={googleDrivePreviewUrl(activeJourneyLesson.video_url)}
                                    title={`Video: ${activeJourneyLesson.title}`}
                                    allow="autoplay; encrypted-media"
                                    allowFullScreen
                                  />
                                  <a
                                    className="training-drive-fallback"
                                    href={activeJourneyLesson.video_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    ¿No carga el video? Abrir en Google Drive ↗
                                  </a>
                                </>
                              ) : (
                                <a
                                  className="btn btn-ghost"
                                  href={activeJourneyLesson.video_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Abrir video ↗
                                </a>
                              )}
                            </div>
                          )}

                          {activeJourneyLesson.external_url && (
                            <a
                              className="training-resource-card"
                              href={activeJourneyLesson.external_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <span>↗</span>
                              <div>
                                <strong>Abrir recurso</strong>
                                <small>Se abrirá en una pestaña nueva.</small>
                              </div>
                            </a>
                          )}

                          {activeJourneyLesson.content_type === "CHECKLIST" && (
                            activeJourneyLesson.checklist_items?.length > 0 ? (
                              <div className="training-checklist-card training-checklist-items">
                                <div className="training-checklist-heading">
                                  <strong>Tus primeros pasos</strong>
                                  <span>
                                    {(activeJourneyLesson.checklist_completed_items || []).length}
                                    /{activeJourneyLesson.checklist_items.length}
                                  </span>
                                </div>
                                {activeJourneyLesson.checklist_items.map((item, index) => {
                                  const checked = (activeJourneyLesson.checklist_completed_items || []).includes(index);
                                  return (
                                    <label className={checked ? "is-checked" : ""} key={item}>
                                      <input
                                        type="checkbox"
                                        checked={checked}
                                        disabled={activeJourneyLesson.completed || checklistSavingLessonId === activeJourneyLesson.id}
                                        onChange={(event) => {
                                          void updateChecklistItem(
                                            activeJourneyLesson,
                                            index,
                                            event.target.checked,
                                          );
                                        }}
                                      />
                                      <span>{item}</span>
                                    </label>
                                  );
                                })}
                                <small>
                                  El avance se guarda automáticamente. Puedes salir y continuar después.
                                </small>
                              </div>
                            ) : (
                              <div className="training-checklist-card">
                                <strong>Antes de continuar</strong>
                                <span>Confirma que revisaste los puntos de esta actividad con tu líder o responsable.</span>
                              </div>
                            )
                          )}

                          <div className="training-journey-actions">
                            {!isTeamModule(activeModule) && (
                              <button
                                className="btn btn-secondary"
                                type="button"
                                disabled={!previousJourneyLesson}
                                onClick={() => previousJourneyLesson && selectLesson(previousJourneyLesson.id)}
                              >
                                ← Anterior
                              </button>
                            )}
                            <div>
                              {activeJourneyLesson.completed ? (
                                <span className="status-pill">
                                  <i /> {isTeamModule(activeModule) ? "Video completado" : "Lección completada"}
                                </span>
                              ) : (
                                activeJourneyLesson.content_type === "CHECKLIST"
                                && activeJourneyLesson.checklist_items?.length > 0
                              ) ? (
                                <span className="training-checklist-progress-label">
                                  Completa todos los puntos para continuar
                                </span>
                              ) : activeJourneyLesson.content_type === "VIDEO" ? (
                                <span className="training-checklist-progress-label">
                                  {isDirectVideo(activeJourneyLesson.video_url)
                                    ? `${Math.round(Number(activeJourneyLesson.video_progress?.watched_percent || 0))}% reproducido · mínimo 80%`
                                    : "Este video debe estar alojado en Talent para validar el 80% reproducido."}
                                </span>
                              ) : (
                                <button
                                  className="btn btn-primary"
                                  type="button"
                                  onClick={() => completeLesson(activeJourneyLesson.id)}
                                  disabled={saving}
                                >
                                  {saving ? "Guardando…" : "✓ Marcar lección como completada"}
                                </button>
                              )}
                              {activeJourneyLesson.completed
                                && nextRequiredJourneyLesson
                                && !isTeamModule(activeModule) && (
                                  <button
                                    className="btn btn-primary"
                                    type="button"
                                    onClick={() => selectLesson(nextRequiredJourneyLesson.id)}
                                  >
                                    Continuar →
                                  </button>
                                )}
                              {activeJourneyLesson.completed
                                && !nextRequiredJourneyLesson
                                && employeeCourse.course.has_quiz
                                && !selectedAssignment?.quiz_result?.passed && (
                                  <button
                                    className="btn btn-primary"
                                    type="button"
                                    onClick={openFinalQuiz}
                                  >
                                    Ir a evaluación final →
                                  </button>
                                )}
                            </div>
                          </div>
                        </>
                      ) : (
                        <EmptyState
                          compact
                          icon="check"
                          title="Ruta lista"
                          description="No hay más actividades para mostrar."
                        />
                      )}
                    </article>
                  </div>

                  <TrainingEmployeeQuiz
                    course={employeeCourse.course}
                    quiz={employeeQuiz}
                    answers={quizAnswers}
                    onAnswerChange={(questionId, optionIndex) => setQuizAnswers((current) => ({
                      ...current,
                      [questionId]: optionIndex,
                    }))}
                    result={quizResult}
                    onSubmit={submitQuiz}
                    saving={saving}
                  />
                </>
              ) : (
                <EmptyState
                  icon="training"
                  title="Selecciona un curso"
                  description="Abre una capacitación para ver sus módulos y lecciones."
                />
              )}
            </section>
          </div>
        )}
      </section>
  );
}
