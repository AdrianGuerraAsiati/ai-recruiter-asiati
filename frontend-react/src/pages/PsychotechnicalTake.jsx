// eslint-disable-next-line no-unused-vars
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import "./Psychotechnical.css";

const COMMON_SENSE = "COMMON_SENSE_GTH_F016";
const TEMPERAMENT = "TEMPERAMENT_GTH_F017";
const VALANTI = "VALANTI_ASIATI";
const ATTENTION = "ATTENTION_DETAIL_V00";

function formatTimer(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
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
  const [remainingSeconds, setRemainingSeconds] = useState(null);

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

  useEffect(() => {
    if (phase !== "test" || assignment?.test_key !== ATTENTION || remainingSeconds == null || remainingSeconds <= 0) {
      return undefined;
    }
    const id = window.setInterval(() => {
      setRemainingSeconds((current) => Math.max(0, Number(current || 0) - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [assignment?.test_key, phase, remainingSeconds]);

  async function start() {
    setError("");
    try {
      const { data } = await api.post(`/public/psychotechnical/${token}/start`);
      setAssignment(data.assignment);
      setQuestions(data.questions || []);
      setAnswers({});
      setRemainingSeconds(
        data.assignment?.test_key === ATTENTION
          ? Number(data.assignment?.duration_seconds || 440)
          : null,
      );
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
  const timeExpired = timed && remainingSeconds === 0;
  const requiresAllAnswers = assignment?.test_key !== ATTENTION;
  const canSubmit = requiresAllAnswers
    ? answered === questions.length && questions.length > 0
    : answered > 0;

  async function submit(event) {
    event.preventDefault();
    if (!canSubmit || submitting) return;
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
      setError(getApiErrorMessage(requestError, {
        action: "enviar las respuestas",
        resource: "prueba psicotécnica",
        fallback: "No fue posible enviar tus respuestas. Intenta nuevamente.",
      }));
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "loading") {
    return <main className="psychotechnical-public"><div className="psychotechnical-public-card"><p>Cargando prueba…</p></div></main>;
  }

  if (phase === "error") {
    return (
      <main className="psychotechnical-public">
        <div className="psychotechnical-public-card">
          <span className="eyebrow">Talent Intelligence · ASIATI</span>
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
          <span className="eyebrow">Talent Intelligence · ASIATI</span>
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
          <span className="eyebrow">Talent Intelligence · ASIATI</span>
          <div className="psychotechnical-public-code">{assignment?.test_code} · v{assignment?.source_version}</div>
          <h1>{assignment?.test_name || "Prueba psicotécnica"}</h1>
          <p>{assignment?.test_description}</p>

          <div className="psychotechnical-public-summary">
            <div><span>Ítems</span><strong>{assignment?.question_count}</strong></div>
            <div><span>Tiempo estimado</span><strong>{assignment?.duration_minutes} min</strong></div>
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

          {assignment?.test_key === ATTENTION && (
            <div className="psychotechnical-time-warning">
              <strong>Prueba con tiempo.</strong>
              <span>Al comenzar tendrás {formatTimer(assignment?.duration_seconds || 440)}. Cuando llegue a 00:00 ya no podrás modificar respuestas.</span>
            </div>
          )}

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
            {timed ? (
              <>
                <strong className={timeExpired ? "is-expired" : ""}>{formatTimer(remainingSeconds)}</strong>
                <span>{timeExpired ? "tiempo finalizado" : "tiempo restante"}</span>
              </>
            ) : (
              <>
                <strong>{answered}/{questions.length}</strong>
                <span>respondidas</span>
              </>
            )}
          </div>
          <div className="psychotechnical-progress-track" aria-label={`Progreso ${progress}%`}>
            <i style={{ width: `${progress}%` }} />
          </div>
        </header>

        {timeExpired && (
          <div className="psychotechnical-expired-banner" role="status">
            El tiempo terminó. Tus respuestas quedaron bloqueadas; envía lo que alcanzaste a completar.
          </div>
        )}

        {groups.map((group) => (
          <section className="psychotechnical-question-group" key={group.key}>
            <h2>{group.title}</h2>
            <p className="psychotechnical-group-description">{group.description}</p>

            {group.items.map((question) => {
              const questionNumber = questions.findIndex((item) => item.id === question.id) + 1;
              const selected = answers[question.id];

              if (question.kind === "paired_allocation") {
                return (
                  <fieldset className="psychotechnical-question psychotechnical-question--pair" key={question.id} disabled={timeExpired}>
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
                <fieldset className="psychotechnical-question" key={question.id} disabled={timeExpired}>
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
            <strong>
              {requiresAllAnswers
                ? (answered === questions.length ? "Todas las preguntas respondidas" : `Faltan ${questions.length - answered} respuestas`)
                : (timeExpired ? "Tiempo finalizado" : `${answered} de ${questions.length} respondidas`)}
            </strong>
            <span>
              {requiresAllAnswers
                ? "Revisa tus respuestas antes de enviar."
                : "En Atención al Detalle la eficiencia considera cuántos ítems alcanzaste a responder."}
            </span>
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
