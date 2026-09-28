// eslint-disable-next-line no-unused-vars
import React from "react";

import { EmptyState } from "../../components/ui/StatePanel";

export default function TrainingAdminQuiz({
  course,
  quizForm,
  onQuizFormChange,
  onCreateQuiz,
  questionForm,
  onQuestionFormChange,
  onQuestionOptionChange,
  onAddQuestion,
  saving,
}) {
  return (
    <section className="panel training-quiz-admin">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Evaluación</span>
          <h2>Quiz del curso</h2>
        </div>
        {course.quiz && (
          <span className="training-status training-status-published">
            Aprueba con {course.quiz.passing_score}%
          </span>
        )}
      </div>

      {!course.quiz ? (
        course.status === "DRAFT" ? (
          <form className="training-quiz-create-form" onSubmit={onCreateQuiz}>
            <div className="training-inline-grid">
              <input
                aria-label="Título de la evaluación"
                value={quizForm.title}
                onChange={(event) => onQuizFormChange({ title: event.target.value })}
                placeholder="Evaluación final"
                required
              />
              <input
                aria-label="Puntaje mínimo para aprobar"
                type="number"
                min="1"
                max="100"
                value={quizForm.passing_score}
                onChange={(event) => onQuizFormChange({ passing_score: event.target.value })}
                required
              />
            </div>
            <button className="btn btn-secondary" type="submit" disabled={saving}>
              + Crear evaluación
            </button>
          </form>
        ) : (
          <EmptyState
            compact
            icon="training"
            title="Curso sin evaluación"
            description="Este curso se completa únicamente con sus lecciones."
          />
        )
      ) : (
        <div className="training-quiz-admin-body">
          <div className="training-quiz-summary">
            <div>
              <strong>{course.quiz.title}</strong>
              <small>
                {course.quiz.question_count} preguntas · mínimo {course.quiz.passing_score}%
              </small>
            </div>
          </div>

          {course.quiz.questions?.length > 0 && (
            <div className="training-quiz-question-list">
              {course.quiz.questions.map((question) => (
                <article className="training-quiz-question-admin" key={question.id}>
                  <span>{question.position}</span>
                  <div>
                    <strong>{question.prompt}</strong>
                    <ol type="A">
                      {question.options.map((option, index) => (
                        <li
                          className={index === question.correct_option ? "is-correct" : ""}
                          key={option}
                        >
                          {option}
                        </li>
                      ))}
                    </ol>
                  </div>
                </article>
              ))}
            </div>
          )}

          {course.status === "DRAFT" && (
            <form className="training-quiz-question-form" onSubmit={onAddQuestion}>
              <strong>Nueva pregunta</strong>
              <textarea
                aria-label="Pregunta de evaluación"
                rows="2"
                value={questionForm.prompt}
                onChange={(event) => onQuestionFormChange({ prompt: event.target.value })}
                placeholder="Escribe la pregunta"
                required
              />
              <div className="training-quiz-options-grid">
                {questionForm.options.map((option, index) => (
                  <input
                    key={index}
                    aria-label={`Opción ${index + 1}`}
                    value={option}
                    onChange={(event) => onQuestionOptionChange(index, event.target.value)}
                    placeholder={`Opción ${index + 1}`}
                    required
                  />
                ))}
              </div>
              <div className="training-quiz-question-actions">
                <select
                  aria-label="Respuesta correcta"
                  value={questionForm.correct_option}
                  onChange={(event) => onQuestionFormChange({ correct_option: event.target.value })}
                >
                  {questionForm.options.map((_, index) => (
                    <option key={index} value={String(index)}>
                      Correcta: opción {index + 1}
                    </option>
                  ))}
                </select>
                <button className="btn btn-secondary" type="submit" disabled={saving}>
                  Agregar pregunta
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </section>
  );
}
