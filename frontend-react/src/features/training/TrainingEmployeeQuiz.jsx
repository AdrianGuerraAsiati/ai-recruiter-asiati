// eslint-disable-next-line no-unused-vars
import React from "react";

import { LoadingState } from "../../components/ui/StatePanel";

export default function TrainingEmployeeQuiz({
  course,
  quiz,
  answers,
  onAnswerChange,
  result,
  onSubmit,
  saving,
}) {
  if (!course?.has_quiz) return null;

  return (
    <section className="training-quiz-employee" id="training-final-quiz">
      <div className="training-quiz-employee-heading">
        <div>
          <span className="eyebrow">Evaluación final</span>
          <h3>{quiz?.title || "Quiz del curso"}</h3>
        </div>
        {quiz && (
          <span className="training-status training-status-published">
            Mínimo {quiz.passing_score}%
          </span>
        )}
      </div>

      {course.completed_lessons < course.lesson_count ? (
        <div className="training-quiz-lock">
          <strong>Completa todas las lecciones para habilitar la evaluación.</strong>
        </div>
      ) : quiz ? (
        <form className="training-quiz-attempt-form" onSubmit={onSubmit}>
          {quiz.attempts?.length > 0 && (
            <div className="training-quiz-attempt-history">
              <span>Intentos anteriores</span>
              {quiz.attempts.map((attempt) => (
                <b
                  className={attempt.passed ? "score-positive" : "score-negative"}
                  key={attempt.id}
                >
                  #{attempt.attempt_number}: {attempt.score_percent}% {attempt.passed ? "✓" : ""}
                </b>
              ))}
            </div>
          )}

          {quiz.questions.map((question, questionIndex) => (
            <fieldset className="training-quiz-question" key={question.id}>
              <legend>{questionIndex + 1}. {question.prompt}</legend>
              {question.options.map((option, optionIndex) => (
                <label key={option}>
                  <input
                    type="radio"
                    name={`quiz-${question.id}`}
                    value={optionIndex}
                    checked={answers[question.id] === optionIndex}
                    onChange={() => onAnswerChange(question.id, optionIndex)}
                    required
                  />
                  <span>{option}</span>
                </label>
              ))}
            </fieldset>
          ))}

          {result?.attempt && (
            <div className={`training-quiz-result ${result.attempt.passed ? "is-pass" : "is-fail"}`}>
              <strong>{result.attempt.score_percent}%</strong>
              <span>
                {result.attempt.passed
                  ? "Evaluación aprobada. Curso completado."
                  : `Aún no alcanzas el ${result.passing_score}%. Puedes intentarlo de nuevo.`}
              </span>
            </div>
          )}

          <button
            className="btn btn-primary"
            type="submit"
            disabled={saving || Object.keys(answers).length !== quiz.question_count}
          >
            {saving ? "Enviando…" : "Enviar evaluación"}
          </button>
        </form>
      ) : (
        <LoadingState label="Preparando evaluación…" compact />
      )}
    </section>
  );
}
