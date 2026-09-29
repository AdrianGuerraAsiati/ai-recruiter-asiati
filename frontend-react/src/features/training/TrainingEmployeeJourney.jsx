// eslint-disable-next-line no-unused-vars
import React from "react";

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
  saving,
  nextRequiredJourneyLesson,
  openFinalQuiz,
  employeeQuiz,
  quizAnswers,
  setQuizAnswers,
  quizResult,
  submitQuiz,
}) {
  const modules = employeeCourse?.course?.modules || [];
  const activeModule = modules.find(
    (module) => module.id === activeJourneyLesson?.module?.id,
  ) || modules[0] || null;

  function moduleLabel(module) {
    return String(module?.title || "")
      .replace(/^Módulo\s+\d+\s*·\s*/i, "")
      .trim();
  }

  function openModule(module) {
    const lessons = module?.lessons || [];
    const nextLesson = lessons.find(
      (lesson) => !lesson.completed && !lesson.is_optional,
    )
      || lessons.find((lesson) => !lesson.completed)
      || lessons[0];
    if (nextLesson) setActiveLessonId(nextLesson.id);
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
          <div className="training-learning-layout">
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

            <section className="panel training-player-panel">
              {detailLoading && !employeeCourse ? (
                <LoadingState label="Cargando contenido…" compact />
              ) : employeeCourse?.course ? (
                <>
                  <div className="training-player-heading">
                    <div>
                      <span className="eyebrow">Curso asignado</span>
                      <h2>{employeeCourse.course.title}</h2>
                      <p>{employeeCourse.course.description || "Capacitación ASIATI"}</p>
                    </div>
                    <strong>{employeeCourse.course.progress_percent}%</strong>
                  </div>

                  <div className="training-journey-overview">
                    <div className="training-journey-progress-copy">
                      <span>Tu avance</span>
                      <strong>{employeeCourse.course.progress_percent}%</strong>
                      <small>
                        {employeeCourse.course.completed_lessons} de {employeeCourse.course.lesson_count} actividades obligatorias
                        {employeeCourse.course.remaining_minutes
                          ? ` · ~${employeeCourse.course.remaining_minutes} min restantes`
                          : ""}
                        {employeeCourse.course.has_unknown_remaining_duration
                          ? " + contenido con duración por confirmar"
                          : ""}
                      </small>
                    </div>
                    <ProgressBar value={employeeCourse.course.progress_percent} />
                  </div>

                  <section className="training-focus-session">
                    <div className="training-focus-session-copy">
                      <span className="eyebrow">Sesión recomendada</span>
                      <h3>
                        {currentRecommendedSession.items.length > 0
                          ? `${currentRecommendedSession.items.length} actividad${currentRecommendedSession.items.length === 1 ? "" : "es"} para avanzar`
                          : employeeCourse.course.has_quiz && !selectedAssignment?.quiz_result?.passed
                            ? "Ya puedes presentar la evaluación"
                            : "Ruta de contenido completada"}
                      </h3>
                      <p>
                        {currentRecommendedSession.items.length > 0
                          ? "Avanza en un bloque corto. Tu progreso queda guardado automáticamente."
                          : employeeCourse.course.has_quiz && !selectedAssignment?.quiz_result?.passed
                            ? "Terminaste el contenido obligatorio. Solo falta el quiz final."
                            : "Completaste las actividades obligatorias de esta ruta."}
                      </p>
                    </div>

                    {currentRecommendedSession.items.length > 0 && (
                      <div className="training-focus-session-items">
                        {currentRecommendedSession.items.map((lesson) => (
                          <span key={lesson.id}>
                            {lessonTypeIcon(lesson.content_type)} {lesson.title}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="training-focus-session-actions">
                      {currentRecommendedSession.items.length > 0 && (
                        <span className="training-focus-session-time">
                          {currentRecommendedSession.minutes > 0
                            ? `~${currentRecommendedSession.minutes} min`
                            : "Duración por confirmar"}
                          {currentRecommendedSession.hasUnknownDuration
                            && currentRecommendedSession.minutes > 0
                            ? " + contenido por confirmar"
                            : ""}
                        </span>
                      )}
                      {currentRecommendedSession.items.length > 0 ? (
                        <button
                          className="btn btn-primary"
                          type="button"
                          onClick={() => setActiveLessonId(currentRecommendedSession.items[0].id)}
                        >
                          Continuar ahora →
                        </button>
                      ) : employeeCourse.course.has_quiz && !selectedAssignment?.quiz_result?.passed ? (
                        <button
                          className="btn btn-primary"
                          type="button"
                          onClick={openFinalQuiz}
                        >
                          Ir a evaluación final →
                        </button>
                      ) : null}
                    </div>
                  </section>

                  <nav
                    className="training-module-switcher-shell"
                    aria-label="Módulos del curso"
                  >
                    <div className="training-module-switcher">
                      {modules.map((module) => {
                        const isActive = activeModule?.id === module.id;
                        return (
                          <button
                            key={module.id}
                            type="button"
                            className={`training-module-tab ${isActive ? "active" : ""} ${module.is_complete ? "is-complete" : ""}`}
                            aria-current={isActive ? "step" : undefined}
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

                  <div className="training-journey-layout">
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
                                onClick={() => setActiveLessonId(lesson.id)}
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
                                    {isTeamModule(activeModule) ? "Conoce al equipo" : lessonTypeLabel(lesson.content_type)}
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

                    <article className="training-journey-focus">
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
                                <video
                                  key={activeJourneyLesson.id}
                                  controls
                                  preload="metadata"
                                  src={activeJourneyLesson.video_url}
                                  aria-label={`Video: ${activeJourneyLesson.title}`}
                                >
                                  Tu navegador no puede reproducir este video.
                                </video>
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
                            <button
                              className="btn btn-secondary"
                              type="button"
                              disabled={!previousJourneyLesson}
                              onClick={() => previousJourneyLesson && setActiveLessonId(previousJourneyLesson.id)}
                            >
                              ← Anterior
                            </button>
                            <div>
                              {activeJourneyLesson.completed ? (
                                <span className="status-pill"><i /> Lección completada</span>
                              ) : (
                                activeJourneyLesson.content_type === "CHECKLIST"
                                && activeJourneyLesson.checklist_items?.length > 0
                              ) ? (
                                <span className="training-checklist-progress-label">
                                  Completa todos los puntos para continuar
                                </span>
                              ) : (
                                <button
                                  className="btn btn-primary"
                                  type="button"
                                  onClick={() => completeLesson(activeJourneyLesson.id)}
                                  disabled={saving}
                                >
                                  {saving
                                    ? "Guardando…"
                                    : "✓ Marcar lección como completada"}
                                </button>
                              )}
                              {activeJourneyLesson.completed && nextRequiredJourneyLesson && (
                                <button
                                  className="btn btn-primary"
                                  type="button"
                                  onClick={() => setActiveLessonId(nextRequiredJourneyLesson.id)}
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
