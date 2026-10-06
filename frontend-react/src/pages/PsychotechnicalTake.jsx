// eslint-disable-next-line no-unused-vars
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import "./Psychotechnical.css";

export default function PsychotechnicalTake() {
  const { token } = useParams();
  const [assignment, setAssignment] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

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

  const grouped = useMemo(() => questions.reduce((acc, question) => {
    const key = question.dimension;
    if (!acc[key]) acc[key] = [];
    acc[key].push(question);
    return acc;
  }, {}), [questions]);

  async function submit(event) {
    event.preventDefault();
    if (answered !== questions.length || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await api.post(`/public/psychotechnical/${token}/submit`, {
        answers: questions.map((question) => ({
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
          <small>No necesitas volver a enviar la prueba.</small>
        </div>
      </main>
    );
  }

  if (phase === "intro") {
    return (
      <main className="psychotechnical-public">
        <div className="psychotechnical-public-card">
          <span className="eyebrow">Talent Intelligence · ASIATI</span>
          <h1>{assignment?.test_name || "Prueba psicotécnica"}</h1>
          <p>{assignment?.test_description}</p>

          <div className="psychotechnical-public-summary">
            <div><span>Preguntas</span><strong>{assignment?.question_count}</strong></div>
            <div><span>Tiempo estimado</span><strong>{assignment?.duration_minutes} min</strong></div>
            <div><span>Candidato</span><strong>{assignment?.candidate_name || "Asignado"}</strong></div>
          </div>

          <div className="psychotechnical-public-notice">
            <strong>Antes de comenzar</strong>
            <p>
              Esta es una prueba laboral objetiva. No evalúa salud mental ni realiza diagnósticos de personalidad.
              Su resultado es un insumo complementario y no determina por sí solo una decisión de contratación.
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
            <span className="eyebrow">Prueba en curso</span>
            <h1>{assignment?.test_name}</h1>
            <p>Selecciona una respuesta en cada pregunta.</p>
          </div>
          <div className="psychotechnical-progress-copy">
            <strong>{answered}/{questions.length}</strong>
            <span>respondidas</span>
          </div>
          <div className="psychotechnical-progress-track" aria-label={`Progreso ${progress}%`}>
            <i style={{ width: `${progress}%` }} />
          </div>
        </header>

        {Object.entries(grouped).map(([dimension, dimensionQuestions]) => (
          <section className="psychotechnical-question-group" key={dimension}>
            <h2>{dimensionQuestions[0]?.dimension === "LOGICAL" ? "Razonamiento lógico"
              : dimensionQuestions[0]?.dimension === "NUMERICAL" ? "Razonamiento numérico"
                : dimensionQuestions[0]?.dimension === "ATTENTION" ? "Atención al detalle"
                  : "Comprensión verbal"}</h2>
            {dimensionQuestions.map((question) => (
              <fieldset className="psychotechnical-question" key={question.id}>
                <legend>{questions.findIndex((item) => item.id === question.id) + 1}. {question.prompt}</legend>
                <div className="psychotechnical-options">
                  {question.options.map((option) => (
                    <label
                      key={option.id}
                      className={answers[question.id] === option.id ? "is-selected" : ""}
                    >
                      <input
                        type="radio"
                        name={question.id}
                        value={option.id}
                        checked={answers[question.id] === option.id}
                        onChange={() => setAnswers((current) => ({
                          ...current,
                          [question.id]: option.id,
                        }))}
                      />
                      <span>{option.label}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ))}
          </section>
        ))}

        {error && <p className="psychotechnical-public-error">{error}</p>}

        <footer className="psychotechnical-submit-bar">
          <div>
            <strong>{answered === questions.length ? "Todas las preguntas respondidas" : `Faltan ${questions.length - answered} respuestas`}</strong>
            <span>Revisa tus respuestas antes de enviar.</span>
          </div>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={answered !== questions.length || submitting}
          >
            {submitting ? "Enviando…" : "Enviar prueba"}
          </button>
        </footer>
      </form>
    </main>
  );
}
