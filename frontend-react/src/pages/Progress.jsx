// eslint-disable-next-line no-unused-vars
import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";
import { useSession } from "../context/SessionContext";


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
        setError(err.response?.data?.detail || "No fue posible cargar tu progreso.");
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
    return <div className="page"><div className="page-loading"><span /> Cargando tu progreso…</div></div>;
  }

  const firstName = principal?.profile?.first_name || "equipo";

  return (
    <div className="page progress-page">
      <header className="page-header split-header">
        <div>
          <span className="eyebrow">Desarrollo personal</span>
          <h1>Mi progreso</h1>
          <p>{firstName}, aquí puedes revisar tus cursos asignados y el avance acumulado.</p>
        </div>
        <Link className="btn btn-primary" to="/training">Continuar capacitación</Link>
      </header>

      {error && <div className="alert" role="alert">{error}</div>}

      <section className="metrics-grid" aria-label="Resumen de progreso">
        <article className="metric-card metric-blue"><span className="metric-label">Cursos asignados</span><strong className="metric-value">{assignments.length}</strong><small>Ruta personal de aprendizaje</small></article>
        <article className="metric-card metric-cyan"><span className="metric-label">Completados</span><strong className="metric-value">{summary.completed}</strong><small>Cursos finalizados</small></article>
        <article className="metric-card metric-violet"><span className="metric-label">Progreso general</span><strong className="metric-value">{summary.progress}%</strong><small>Promedio de tus cursos</small></article>
        <article className="metric-card"><span className="metric-label">Evaluaciones aprobadas</span><strong className="metric-value">{summary.evaluationsPassed}</strong><small>Resultados superados</small></article>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span className="eyebrow">Detalle</span><h2>Mis capacitaciones</h2></div></div>
        {assignments.length === 0 ? (
          <div className="empty-state compact"><strong>Aún no tienes capacitaciones asignadas</strong><p>Cuando se te asigne un curso aparecerá aquí automáticamente.</p></div>
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
