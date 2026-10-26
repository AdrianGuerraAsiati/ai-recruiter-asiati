// eslint-disable-next-line no-unused-vars
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import "./Psychotechnical.css";

const TEMPERAMENT = "TEMPERAMENT_GTH_F017";
const VALANTI = "VALANTI_ASIATI";
const ATTENTION = "ATTENTION_DETAIL_V00";

function formatTime(totalSeconds) {
  const safe = Math.max(0, Math.ceil(totalSeconds || 0));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

function instructionsFor(assignment) {
  if (assignment?.test_key === VALANTI) {
    return "En cada par distribuye exactamente tres puntos usando una de las opciones 3-0, 0-3, 2-1 o 1-2. En la segunda parte el puntaje mayor corresponde a la frase que consideras más inaceptable.";
  }
  if (assignment?.test_key === TEMPERAMENT) {
    return "Selecciona la opción que mejor describa tu comportamiento habitual en el entorno laboral. No hay respuestas correctas o incorrectas.";
  }
  if (assignment?.test_key === ATTENTION) {
    return "Trabaja con rapidez y precisión. Esta versión digital conserva tareas alfanuméricas, comparación de letras y figuras adaptadas a pantalla.";
  }
  return "Lee cada situación y selecciona la respuesta que consideres más lógica y adecuada en un contexto organizacional.";
}

function groupQuestions(assignment, questions) {
  if (assignment?.test_key === VALANTI) {
    return [
      {
        key: "PART_1",
        title: "Primera parte · importancia personal",
        description: "El puntaje mayor corresponde a la frase que tiene más importancia para ti.",
        items: questions.filter((question) => question.part === 1),
      },
      {
        key: "PART_2",
        title: "Segunda parte · inaceptabilidad",
        description: "El puntaje mayor corresponde a la frase que consideras peor o más inaceptable.",
        items: questions.filter((question) => question.part === 2),
      },
    ];
  }

  if (assignment?.test_key === ATTENTION) {
    const order = ["ALPHANUMERIC", "LETTERS", "FIGURES"];
    return order.map((section) => {
      const items = questions.filter((question) => question.section === section);
      return {
        key: section,
        title: items[0]?.section_label || section,
        description: section === "ALPHANUMERIC"
          ? "Selecciona el código idéntico al modelo."
          : section === "LETTERS"
            ? "Marca 0 si las cadenas son iguales y 1 si son diferentes."
            : "Selecciona la figura exactamente igual al modelo.",
        items,
      };
    }).filter((group) => group.items.length > 0);
  }

  return [{
    key: "ALL",
    title: assignment?.test_name || "Prueba",
    description: instructionsFor(assignment),
    items: questions,
  }];
}

export default function PsychotechnicalTake() {
  const { token } = useParams();
  const [assignment, setAssignment] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deadlineMs, setDeadlineMs] = useState(null);
  const [secondsLeft, setSecondsLeft] = useState(null);
  const timeoutSubmitted = useRef(false);

  useEffect(() => {
    let cancelled = false;
    api.get(`/public/psychotechnical/${token}`)
      .then(({ data }) => {
        if (cancelled) return;
        setAssignment(data);
        setPhase(data?.status === "COMPLETED" ? "completed" : "intro");
      })
      .catch((requestError) => {
        if (cancelled) return;
        setError(getApiErrorMessage(requestError, {
          action: "abrir la prueba",
          resource: "prueba psicotécnica",
          fallback: "El enlace no es válido o ya expiró.",
        }));
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function start() {
    setError("");
    try {
      const { data } = await api.post(`/public/psychotechnical/${token}/start`);
      setAssignment(data.assignment);
      setQuestions(data.questions || []);
      setAnswers({});
      timeoutSubmitted.current = false;
      if (data.assignment?.test_key === ATTENTION &&
          Number.isFinite(Number(data.assignment?.time_remaining_seconds))) {
        const remaining = Math.max(0, Number(data.assignment.time_remaining_seconds));
        setDeadlineMs(Date.now() + remaining * 1000);
        setSecondsLeft(remaining);
      } else {
        setDeadlineMs(null);
        setSecondsLeft(null);
      }
      setPhase("test");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, {
        action: "iniciar la prueba",
        resource: "prueba psicotécnica",
      }));
    }
  }

  const answered = Object.keys(answers).length;
  const progress = questions.length ? Math.round((answered / questions.length) * 100) : 0;
  const groups = useMemo(
    () => groupQuestions(assignment, questions),
    [assignment, questions],
  );
  const timed = assignment?.test_key === ATTENTION;
  const canSubmit = questions.length > 0 && (timed ? answered > 0 : answered === questions.length);

  const submitAnswers = useCallback(async (automatic = false) => {
    if ((!automatic && !canSubmit) || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await api.post(`/public/psychotechnical/${token}/submit`, {
        answers: questions
          .filter((question) => answers[question.id] != null)
          .map((question) => ({
            question_id: question.id,
            option_id: answers[question.id],
          })),
      });
      setPhase("completed");
    } catch (requestError) {
      if (requestError?.response?.status === 410) {
        setPhase("error");
      }
      setError(getApiErrorMessage(requestError, {
        action: "enviar las respuestas",
        resource: "prueba psicotécnica",
        fallback: "No fue posible enviar tus respuestas. Intenta nuevamente.",
      }));
    } finally {
      setSubmitting(false);
    }
  }, [answers, canSubmit, questions, submitting, token]);

  useEffect(() => {
    if (phase !== "test" || deadlineMs === null) return undefined;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((deadlineMs - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining === 0 && !timeoutSubmitted.current) {
        timeoutSubmitted.current = true;
        // The scoring engine permits partial (including empty) attention answers.
        void submitAnswers(true);
      }
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [deadlineMs, phase, submitAnswers]);

  function submit(event) {
    event.preventDefault();
    void submitAnswers();
  }

  if (phase === "loading") {
    return <main className="psychotechnical-public"><div className="psychotechnical-public-card"><p>Cargando prueba…</p></div></main>;
  }

  if (phase === "error") {
    return (
      <main className="psychotechnical-public">
        <div className="psychotechnical-public-card">
          <span className="eyebrow">ADN360 · ASIATI</span>
          <h1>No pudimos abrir la prueba</h1>
          <p>{error}</p>
        </div>
      </main>
    );
  }

  if (phase === "completed") {
    return (
      <main className="psychotechnical-public">
        <div className="psychotechnical-public-card psychotechnical-complete">
          <div className="psychotechnical-complete-icon">✓</div>
          <span className="eyebrow">ADN360 · ASIATI</span>
          <h1>Prueba completada</h1>
          <p>Recibimos tus respuestas correctamente. Talento Humano revisará este resultado junto con las demás etapas del proceso.</p>
          <small>No necesitas volver a enviar esta prueba.</small>
        </div>
      </main>
    );
  }

  if (phase === "intro") {
    return (
      <main className="psychotechnical-public">
        <div className="psychotechnical-public-card">
          <div className="psychotechnical-public-kicker">
            <span className="eyebrow">ADN360 · ASIATI</span>
            <span className="psychotechnical-public-code">{assignment?.test_code} · v{assignment?.source_version}</span>
          </div>
          <h1>{assignment?.test_name || "Prueba psicotécnica"}</h1>
          <p>{assignment?.test_description}</p>

          <div className="psychotechnical-public-summary">
            <div><span>Ítems</span><strong>{assignment?.question_count}</strong></div>
            <div><span>Modalidad</span><strong>{assignment?.test_key === ATTENTION ? `Con tiempo: ${formatTime(assignment?.time_limit_seconds ?? assignment?.duration_seconds)}` : "Sin límite de tiempo"}</strong></div>
            <div><span>Candidato</span><strong>{assignment?.candidate_name || "Asignado"}</strong></div>
          </div>

          <div className="psychotechnical-public-notice">
            <strong>Antes de comenzar</strong>
            <p>{instructionsFor(assignment)}</p>
            <p>
              Esta evaluación es un insumo complementario del proceso. No realiza diagnósticos clínicos
              y su resultado no determina por sí solo una contratación.
            </p>
          </div>

          {error && <p className="psychotechnical-public-error">{error}</p>}

          <button className="btn btn-primary psychotechnical-start" type="button" onClick={start}>
            Comenzar prueba
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="psychotechnical-public psychotechnical-public--test">
      <form className="psychotechnical-test-shell" onSubmit={submit}>
        <header className="psychotechnical-test-header">
          <div>
            <span className="eyebrow">{assignment?.test_code} · Prueba en curso</span>
            <h1>{assignment?.test_name}</h1>
            <p>{instructionsFor(assignment)}</p>
          </div>
          <div className="psychotechnical-progress-copy">
            <strong>{answered}/{questions.length}</strong>
            <span>respondidas</span>
            {timed && <span role="timer">Tiempo restante: {formatTime(secondsLeft)}</span>}
          </div>
          <div className="psychotechnical-progress-track" aria-label={`Progreso ${progress}%`}>
            <i style={{ width: `${progress}%` }} />
          </div>
        </header>

        {groups.map((group) => (
          <section className="psychotechnical-question-group" key={group.key}>
            <h2>{group.title}</h2>
            <p className="psychotechnical-group-description">{group.description}</p>

            {group.items.map((question) => {
              const questionNumber = questions.findIndex((item) => item.id === question.id) + 1;
              const selected = answers[question.id];

              if (question.kind === "paired_allocation") {
                return (
                  <fieldset className="psychotechnical-question psychotechnical-question--pair" key={question.id}>
                    <legend>{questionNumber}. Distribuye los 3 puntos</legend>
                    <div className="psychotechnical-valanti-pair">
                      <span>{question.left}</span>
                      <span>{question.right}</span>
                    </div>
                    <div className="psychotechnical-options psychotechnical-options--allocation">
                      {question.options.map((option) => (
                        <label key={option.id} className={selected === option.id ? "is-selected" : ""}>
                          <input
                            type="radio"
                            name={question.id}
                            value={option.id}
                            checked={selected === option.id}
                            onChange={() => setAnswers((current) => ({ ...current, [question.id]: option.id }))}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                );
              }

              return (
                <fieldset className="psychotechnical-question" key={question.id}>
                  <legend>{questionNumber}. {question.prompt}</legend>
                  {question.target && (
                    <div className="psychotechnical-target" aria-label="Modelo a comparar">
                      {question.target}
                    </div>
                  )}
                  <div className="psychotechnical-options">
                    {question.options.map((option) => (
                      <label key={option.id} className={selected === option.id ? "is-selected" : ""}>
                        <input
                          type="radio"
                          name={question.id}
                          value={option.id}
                          checked={selected === option.id}
                          onChange={() => setAnswers((current) => ({ ...current, [question.id]: option.id }))}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              );
            })}
          </section>
        ))}

        {error && <p className="psychotechnical-public-error">{error}</p>}

        <footer className="psychotechnical-submit-bar">
          <div>
            <strong>{answered === questions.length ? "Todas las preguntas respondidas" : `Faltan ${questions.length - answered} respuestas`}</strong>
            <span>{timed ? "Puedes enviar respuestas parciales. Al finalizar el cronómetro se enviará lo respondido automáticamente." : "Responde todas las preguntas y revisa tus respuestas antes de enviar. No hay límite de tiempo."}</span>
          </div>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={!canSubmit || submitting}
          >
            {submitting ? "Enviando…" : "Enviar prueba"}
          </button>
        </footer>
      </form>
    </main>
  );
}
