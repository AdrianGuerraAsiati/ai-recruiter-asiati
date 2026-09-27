// eslint-disable-next-line no-unused-vars
import React, { useEffect, useState } from "react";
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
  ProgressBar,
} from "../components/ui/StatePanel";

function getGreeting(date = new Date()) {
  const hour = date.getHours();

  if (hour >= 5 && hour < 12) return "Buenos días";
  if (hour >= 12 && hour < 19) return "Buenas tardes";
  return "Buenas noches";
}

function Dashboard() {
  const { principal, hasPermission } = useSession();
  const canRecruit = hasPermission("jobs.read") && hasPermission("candidates.read");
  const canManageEmployees = hasPermission("employees.read");
  const [jobs, setJobs] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [trainingAssignments, setTrainingAssignments] = useState([]);
  const [employeeSummary, setEmployeeSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [greeting, setGreeting] = useState(() => getGreeting());
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const updateGreeting = () => setGreeting(getGreeting());
    const intervalId = window.setInterval(updateGreeting, 60_000);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    async function load() {
      try {
        if (canRecruit) {
          const requests = [
            api.get("/jobs"),
            api.get("/candidates"),
          ];
          if (canManageEmployees) {
            requests.push(api.get("/employees/summary"));
          }

          const [jobsResponse, candidatesResponse, employeeSummaryResponse] = await Promise.all(requests);
          const jobsData = jobsResponse.data;
          const candidatesData = candidatesResponse.data;
          setJobs(Array.isArray(jobsData) ? jobsData : jobsData.jobs || []);
          setCandidates(Array.isArray(candidatesData) ? candidatesData : candidatesData.candidates || []);
          if (canManageEmployees && employeeSummaryResponse) {
            setEmployeeSummary(employeeSummaryResponse.data);
          }
        } else {
          const { data } = await api.get("/training/me");
          setTrainingAssignments(Array.isArray(data?.items) ? data.items : []);
        }
      } catch (error) {
        setLoadError(getApiErrorMessage(error, {
          action: "cargar los indicadores del inicio",
          resource: "resumen del workspace",
          fallback: "El inicio no pudo combinar vacantes, candidatos y métricas internas. Recarga la página para volver a consultar los indicadores.",
        }));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [canManageEmployees, canRecruit]);

  if (loading) {
    return <div className="page"><LoadingState label="Preparando tu workspace…" /></div>;
  }

  if (!canRecruit) {
    const firstName = principal?.profile?.first_name || "equipo";
    const completedCourses = trainingAssignments.filter(
      (assignment) => assignment.status === "COMPLETED",
    ).length;
    const overallProgress = trainingAssignments.length
      ? Math.round(
        trainingAssignments.reduce(
          (total, assignment) => total + (assignment.course?.progress_percent || 0),
          0,
        ) / trainingAssignments.length,
      )
      : 0;

    return (
      <div className="page dashboard-page employee-dashboard">
        <PageHeader
          eyebrow="Tu espacio ASIATI"
          title={`${greeting}, ${firstName}.`}
          description="Aquí encontrarás tu proceso de inducción, capacitación y progreso."
          className="dashboard-header"
        />

        {loadError && (
          <FeedbackMessage title="No pudimos actualizar tu espacio">{loadError}</FeedbackMessage>
        )}

        <section className="panel employee-welcome-panel">
          <div className="employee-welcome-copy">
            <span className="eyebrow">Onboarding</span>
            <h2>Conoce ASIATI y cómo trabajamos.</h2>
            <p>
              {trainingAssignments.length
                ? `Tienes ${trainingAssignments.length} curso${trainingAssignments.length === 1 ? "" : "s"} asignado${trainingAssignments.length === 1 ? "" : "s"}.`
                : "Cuando te asignen una capacitación aparecerá aquí automáticamente."}
            </p>
            <span className="employee-onboarding-state">
              Onboarding: {
                principal?.profile?.onboarding_status === "COMPLETED"
                  ? "Completado"
                  : principal?.profile?.onboarding_status === "IN_PROGRESS"
                    ? "En progreso"
                    : principal?.profile?.onboarding_status === "PENDING"
                      ? "Pendiente"
                      : "No requerido"
              }
            </span>
            <Link className="btn btn-primary" to="/training">Ir a capacitación</Link>
          </div>
          <div className="employee-progress-preview" aria-label="Progreso de capacitación">
            <span>Progreso general</span>
            <strong>{overallProgress}%</strong>
            <ProgressBar value={overallProgress} label="Progreso general" />
            <small>
              {trainingAssignments.length
                ? `${completedCourses} de ${trainingAssignments.length} cursos completados`
                : "Aún no tienes cursos asignados."}
            </small>
          </div>
        </section>
      </div>
    );
  }

  const coverage = jobs.length ? Math.min(100, Math.round((candidates.length / jobs.length) * 20)) : 0;

  return (
    <div className="page dashboard-page">
      <PageHeader
        eyebrow="Vista general"
        title={`${greeting}, equipo.`}
        description="Así avanza tu proceso de selección hoy."
        className="dashboard-header"
      />

      {loadError && (
        <FeedbackMessage title="El resumen no está actualizado">{loadError}</FeedbackMessage>
      )}

      <section className="metrics-grid" aria-label="Indicadores principales">
        <MetricCard icon="briefcase" label="Vacantes activas" value={jobs.length} detail="Procesos en seguimiento" tone="blue" live />
        <MetricCard icon="users" label="Talento disponible" value={candidates.length} detail="Perfiles centralizados" tone="cyan" live />
        <MetricCard icon="ranking" label="Cobertura estimada" value={`${coverage}%`} detail="Candidatos por vacante" tone="violet" live />
      </section>

      {canManageEmployees && employeeSummary && (
        <section className="panel onboarding-summary-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Talento Humano</span>
              <h2>Onboarding del equipo</h2>
            </div>
            <Link to="/employees">Ver empleados <span aria-hidden="true">→</span></Link>
          </div>

          <div className="onboarding-summary-grid">
            <div>
              <span>Empleados activos</span>
              <strong>{employeeSummary.active}</strong>
            </div>
            <div>
              <span>Pendientes</span>
              <strong>{employeeSummary.onboarding.pending}</strong>
            </div>
            <div>
              <span>En progreso</span>
              <strong>{employeeSummary.onboarding.in_progress}</strong>
            </div>
            <div>
              <span>Completados</span>
              <strong>{employeeSummary.onboarding.completed}</strong>
            </div>
            <div className="onboarding-summary-progress">
              <span>Finalización onboarding</span>
              <strong>{employeeSummary.onboarding.completion_percent}%</strong>
              <ProgressBar value={employeeSummary.onboarding.completion_percent} label="Finalización onboarding" />
            </div>
          </div>
        </section>
      )}

      <div className="dashboard-grid">
        <section className="panel recent-jobs-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Pipeline</span><h2>Vacantes recientes</h2></div>
            <Link to="/jobs">Ver todas <span aria-hidden="true">→</span></Link>
          </div>

          {jobs.length === 0 ? (
            <EmptyState
              compact
              icon="briefcase"
              title="Aún no hay vacantes"
              description="Crea la primera para comenzar a evaluar talento."
              action={<Link className="btn btn-secondary" to="/jobs">Crear vacante</Link>}
            />
          ) : (
            <div className="job-list">
              {jobs.slice(0, 4).map((job, index) => (
                <article className="job-row" key={job.job_id}>
                  <span className="job-index">{String(index + 1).padStart(2, "0")}</span>
                  <div><h3>{job.title}</h3><p>{job.description}</p></div>
                  <span className="status-pill"><i /> Activa</span>
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="panel intelligence-panel">
          <div className="intelligence-orb"><span>AI</span></div>
          <span className="eyebrow eyebrow-dark">Talent intelligence</span>
          <h2>Del currículum a la evidencia.</h2>
          <p>Compara cada perfil con los requisitos de la vacante y obtén fortalezas, brechas y una recomendación clara.</p>
          <Link className="text-link-light" to="/ranking">Explorar ranking <span aria-hidden="true">↗</span></Link>
        </aside>
      </div>
    </div>
  );
}

export default Dashboard;
