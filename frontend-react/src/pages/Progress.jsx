// eslint-disable-next-line no-unused-vars
import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { useSession } from "../context/SessionContext";
import PageHeader from "../components/ui/PageHeader";
import {
  EmptyState,
  FeedbackMessage,
  LoadingState,
  MetricCard,
} from "../components/ui/StatePanel";


function Progress() {
  const { principal } = useSession();
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const { data } = await api.get("/training/me");
        setAssignments(Array.isArray(data?.items) ? data.items : []);
      } catch (err) {
        setError(getApiErrorMessage(err, {
          action: "cargar tu progreso de capacitación",
          resource: "tu progreso",
          fallback: "Tu progreso no se actualizó. Recarga la página para volver a consultar tus cursos y evaluaciones.",
        }));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const summary = useMemo(() => {
    const completed = assignments.filter((item) => item.status === "COMPLETED").length;
    const progress = assignments.length
      ? Math.round(assignments.reduce((total, item) => total + Number(item.course?.progress_percent || 0), 0) / assignments.length)
      : 0;
    const evaluationsPassed = assignments.filter(
      (item) => item.quiz_result?.passed,
    ).length;
    return { completed, progress, evaluationsPassed };
  }, [assignments]);

  if (loading) {
    return <div className="page"><LoadingState label="Cargando tu progreso…" /></div>;
  }

  const firstName = principal?.profile?.first_name || "equipo";

  return (
    <div className="page progress-page">
      <PageHeader
        eyebrow="Desarrollo personal"
        title="Mi progreso"
        description={`${firstName}, aquí puedes revisar tus cursos asignados y el avance acumulado.`}
        actions={<Link className="btn btn-primary" to="/training">Continuar capacitación</Link>}
        className="split-header"
      />

      {error && <FeedbackMessage title="El progreso no está actualizado">{error}</FeedbackMessage>}

      <section className="metrics-grid" aria-label="Resumen de progreso">
        <MetricCard icon="training" label="Cursos asignados" value={assignments.length} detail="Ruta personal de aprendizaje" tone="blue" />
        <MetricCard icon="check" label="Completados" value={summary.completed} detail="Cursos finalizados" tone="cyan" />
        <MetricCard icon="progress" label="Progreso general" value={`${summary.progress}%`} detail="Promedio de tus cursos" tone="violet" />
        <MetricCard icon="star" label="Evaluaciones aprobadas" value={summary.evaluationsPassed} detail="Resultados superados" />
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span className="eyebrow">Detalle</span><h2>Mis capacitaciones</h2></div></div>
        {assignments.length === 0 ? (
          <EmptyState
            compact
            icon="training"
            title="Aún no tienes capacitaciones asignadas"
            description="Cuando se te asigne un curso aparecerá aquí automáticamente."
          />
        ) : (
          <div className="job-list">
            {assignments.map((assignment, index) => {
              const courseProgress = Number(assignment.course?.progress_percent || 0);
              return (
                <article className="job-row" key={assignment.id}>
                  <span className="job-index">{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h3>{assignment.course?.title || "Capacitación"}</h3>
                    <p>
                      {assignment.course?.completed_lessons || 0} de {assignment.course?.lesson_count || 0} lecciones completadas · {courseProgress}% de avance
                      {assignment.quiz_result
                        ? ` · Evaluación: ${assignment.quiz_result.best_score ?? "sin intento"}${assignment.quiz_result.best_score == null ? "" : "%"}${assignment.quiz_result.passed ? " · Aprobada" : assignment.quiz_result.attempt_count ? " · Pendiente de aprobar" : ""}`
                        : ""}
                    </p>
                  </div>
                  <span className="status-pill"><i /> {assignment.status === "COMPLETED" ? "Completado" : "En progreso"}</span>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

export default Progress;
