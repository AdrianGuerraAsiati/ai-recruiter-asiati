// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

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

function todayInputValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function emptyEmployeeForm() {
  return {
    first_name: "",
    last_name: "",
    email: "",
    job_title: "",
    department: "",
    hire_date: todayInputValue(),
    role: "EMPLOYEE",
  };
}

function Employees() {
  const { principal, hasRole, hasPermission } = useSession();
  const isSuperAdmin = hasRole("SUPER_ADMIN");
  const canReadTrainingResults = hasPermission("training.results.read");
  const [employees, setEmployees] = useState([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [onboardingStatusFilter, setOnboardingStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(() => emptyEmployeeForm());
  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editError, setEditError] = useState("");
  const [onboardingTarget, setOnboardingTarget] = useState(null);
  const [onboardingDetail, setOnboardingDetail] = useState(null);
  const [onboardingDetailLoading, setOnboardingDetailLoading] = useState(false);
  const [onboardingDetailError, setOnboardingDetailError] = useState("");

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (query.trim()) params.q = query.trim();
      if (statusFilter) params.status = statusFilter;
      if (onboardingStatusFilter) params.onboarding_status = onboardingStatusFilter;
      const { data } = await api.get("/employees", { params });
      setEmployees(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar el directorio de empleados",
        resource: "empleados",
        fallback: "El directorio no se actualizó. Mantuvimos tus filtros para que puedas reintentar.",
      }));
    } finally {
      setLoading(false);
    }
  }, [onboardingStatusFilter, query, statusFilter]);

  useEffect(() => {
    const timeoutId = window.setTimeout(loadEmployees, 250);
    return () => window.clearTimeout(timeoutId);
  }, [loadEmployees]);

  const stats = useMemo(() => {
    const active = employees.filter((employee) => employee.status === "ACTIVE").length;
    const admins = employees.filter((employee) =>
      employee.roles?.some((role) => role === "ADMIN" || role === "SUPER_ADMIN")
    ).length;
    const onboardingActive = employees.filter((employee) =>
      ["PENDING", "IN_PROGRESS"].includes(employee.onboarding_status)
    ).length;
    const onboardingCompleted = employees.filter(
      (employee) => employee.onboarding_status === "COMPLETED"
    ).length;
    return { active, admins, onboardingActive, onboardingCompleted };
  }, [employees]);

  async function createEmployee(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.post("/employees", form);
      setForm(emptyEmployeeForm());
      setFormOpen(false);
      await loadEmployees();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "crear el empleado y su acceso",
        resource: "empleados",
        fallback: "El empleado no se creó. Revisa correo, datos personales y permisos antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus(employee) {
    const nextStatus = employee.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    setError("");
    try {
      await api.put(`/employees/${employee.id}/status`, { status: nextStatus });
      await loadEmployees();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cambiar el estado de acceso del empleado",
        resource: "empleados",
        fallback: "El acceso del empleado no cambió. Recarga su estado antes de volver a intentarlo.",
      }));
    }
  }

  function openEmployeeEditor(employee) {
    setEditTarget(employee);
    setEditError("");
    setEditForm({
      job_title: employee.job_title || "",
      department: employee.department || "",
      role: employee.roles?.[0] || "EMPLOYEE",
      onboarding_required:
        employee.onboarding_required ?? employee.onboarding_status !== "NOT_REQUIRED",
    });
  }

  function closeEmployeeEditor() {
    setEditTarget(null);
    setEditForm(null);
    setEditError("");
  }

  async function saveEmployeeEdits(event) {
    event.preventDefault();
    if (!editTarget || !editForm) return;

    setSaving(true);
    setEditError("");
    try {
      const currentRole = editTarget.roles?.[0] || "EMPLOYEE";
      if (editForm.role !== currentRole) {
        await api.put(`/employees/${editTarget.id}/role`, { role: editForm.role });
      }
      await api.put(`/employees/${editTarget.id}`, {
        job_title: editForm.job_title,
        department: editForm.department,
        onboarding_required: editForm.onboarding_required,
      });
      closeEmployeeEditor();
      await loadEmployees();
    } catch (err) {
      setEditError(getApiErrorMessage(err, {
        action: "actualizar el perfil del empleado",
        resource: "empleados",
        fallback: "Los cambios no se guardaron por completo. Revisa cargo, rol y onboarding antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function openOnboardingDetail(employee) {
    if (!employee?.onboarding?.course_id || onboardingDetailLoading) return;
    setOnboardingTarget(employee);
    setOnboardingDetail(null);
    setOnboardingDetailError("");
    setOnboardingDetailLoading(true);
    try {
      const { data } = await api.get(
        `/training/courses/${employee.onboarding.course_id}/assignments/${employee.id}`,
      );
      setOnboardingDetail(data);
    } catch (err) {
      setOnboardingDetailError(
        getApiErrorMessage(err, {
          action: "cargar el detalle de onboarding",
          resource: "onboarding",
          fallback: "El resumen del empleado está disponible, pero no se cargaron sus módulos y avances. Vuelve a abrir el detalle.",
        }),
      );
    } finally {
      setOnboardingDetailLoading(false);
    }
  }

  function closeOnboardingDetail() {
    setOnboardingTarget(null);
    setOnboardingDetail(null);
    setOnboardingDetailError("");
  }

  return (
    <div className="page employees-page">
      <PageHeader
        eyebrow="Gestión interna"
        title="Empleados"
        description="Administra accesos, perfiles, roles y seguimiento de onboarding del equipo ASIATI."
        actions={!formOpen ? (
          <button className="btn btn-primary" type="button" onClick={() => setFormOpen(true)}>
            Crear empleado
          </button>
        ) : null}
        className="split-header"
      />

      {error && <FeedbackMessage title="El directorio no está actualizado">{error}</FeedbackMessage>}

      <section className="metrics-grid employees-metrics" aria-label="Resumen de empleados">
        <MetricCard icon="employee" label="Empleados visibles" value={employees.length} detail="Perfiles encontrados" tone="blue" />
        <MetricCard icon="check" label="Activos" value={stats.active} detail="Con acceso habilitado" tone="cyan" />
        <MetricCard icon="users" label="Administrativos" value={stats.admins} detail="ADMIN o SUPER_ADMIN" tone="violet" />
        <MetricCard icon="progress" label="Onboarding activos" value={stats.onboardingActive} detail="Pendientes o en progreso" />
        <MetricCard icon="training" label="Onboarding completados" value={stats.onboardingCompleted} detail="Ruta finalizada" />
      </section>

      <section className="panel employee-list-panel">
        <div className="employee-toolbar">
          <div>
            <span className="eyebrow">Directorio</span>
            <h2>Equipo ASIATI</h2>
          </div>
          <div className="employee-filters">
            <input
              type="search"
              placeholder="Buscar por nombre, correo, cargo…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Buscar empleados"
            />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              aria-label="Filtrar por estado"
            >
              <option value="">Todos los estados</option>
              <option value="ACTIVE">Activos</option>
              <option value="DISABLED">Deshabilitados</option>
            </select>
            <select
              value={onboardingStatusFilter}
              onChange={(event) => setOnboardingStatusFilter(event.target.value)}
              aria-label="Filtrar por onboarding"
            >
              <option value="">Todo el onboarding</option>
              <option value="PENDING">Pendiente</option>
              <option value="IN_PROGRESS">En progreso</option>
              <option value="COMPLETED">Completado</option>
              <option value="NOT_REQUIRED">No requerido</option>
            </select>
          </div>
        </div>

        {loading ? (
          <LoadingState label="Cargando empleados…" compact />
        ) : employees.length === 0 ? (
          <EmptyState
            compact
            icon="employee"
            title="No hay empleados para mostrar"
            description="Crea el primer perfil o modifica los filtros."
          />
        ) : (
          <div className="employee-table-wrap">
            <table className="employee-table">
              <thead>
                <tr>
                  <th>Empleado</th>
                  <th>Cargo / área</th>
                  <th>Rol</th>
                  <th>Onboarding</th>
                  <th>Estado</th>
                  <th aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => {
                  const role = employee.roles?.[0] || "EMPLOYEE";
                  const isSelf = employee.id === principal?.profile?.id;
                  const canManageTarget = !isSelf && (isSuperAdmin || role !== "SUPER_ADMIN");
                  return (
                    <tr key={employee.id}>
                      <td>
                        <div className="employee-person">
                          <span className="employee-avatar" aria-hidden="true">
                            {(employee.first_name?.[0] || employee.email?.[0] || "?").toUpperCase()}
                          </span>
                          <div>
                            <strong>{[employee.first_name, employee.last_name].filter(Boolean).join(" ") || "Sin nombre"}</strong>
                            <small>{employee.email}</small>
                          </div>
                        </div>
                      </td>
                      <td>
                        <strong className="employee-secondary">{employee.job_title || "Sin cargo"}</strong>
                        <small>{employee.department || "Sin área"}</small>
                      </td>
                      <td>
                        <span className={`role-pill role-${role.toLowerCase()}`}>
                          {role === "SUPER_ADMIN" ? "Super admin" : role === "ADMIN" ? "Administrador" : "Empleado"}
                        </span>
                      </td>
                      <td>
                        <span className={`onboarding-pill onboarding-${String(employee.onboarding_status || "NOT_REQUIRED").toLowerCase()}`}>
                          {employee.onboarding_status === "COMPLETED"
                            ? "Completado"
                            : employee.onboarding_status === "IN_PROGRESS"
                              ? "En progreso"
                              : employee.onboarding_status === "PENDING"
                                ? "Pendiente"
                                : "No requerido"}
                        </span>
                        {employee.onboarding && (
                          <div className="employee-onboarding-progress">
                            <ProgressBar value={employee.onboarding.progress_percent} />
                            <small>{Number(employee.onboarding.progress_percent || 0)}% completado</small>
                            {canReadTrainingResults && (
                              <button
                                className="btn btn-ghost btn-sm employee-onboarding-detail-button"
                                type="button"
                                onClick={() => openOnboardingDetail(employee)}
                              >
                                Ver detalle
                              </button>
                            )}
                          </div>
                        )}
                        {employee.hire_date && <small>Ingreso: {employee.hire_date}</small>}
                      </td>
                      <td>
                        <span className={`status-pill ${employee.status === "ACTIVE" ? "" : "status-disabled"}`}>
                          <i /> {employee.status === "ACTIVE" ? "Activo" : "Deshabilitado"}
                        </span>
                      </td>
                      <td>
                        {canManageTarget && (
                          <div className="ui-actions">
                            <button
                              className="btn btn-ghost"
                              type="button"
                              onClick={() => openEmployeeEditor(employee)}
                            >
                              Editar
                            </button>
                            <button
                              className="btn btn-ghost employee-status-button"
                              type="button"
                              onClick={() => toggleStatus(employee)}
                            >
                              {employee.status === "ACTIVE" ? "Deshabilitar" : "Activar"}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editTarget && editForm && (
        <div className="modal-overlay" role="presentation" onMouseDown={closeEmployeeEditor}>
          <section
            className="modal employee-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="employee-edit-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Equipo ASIATI</span>
                <h2 id="employee-edit-modal-title">Editar integrante</h2>
                <p>
                  {[editTarget.first_name, editTarget.last_name].filter(Boolean).join(" ") || editTarget.email}
                </p>
              </div>
              <button
                className="btn-close"
                type="button"
                aria-label="Cerrar edición"
                onClick={closeEmployeeEditor}
              >
                ×
              </button>
            </div>

            {editError && (
              <FeedbackMessage title="No se guardaron los cambios">{editError}</FeedbackMessage>
            )}

            <form className="employee-form" onSubmit={saveEmployeeEdits}>
              <div className="employee-form-grid">
                <div className="form-group">
                  <label htmlFor="employee-edit-job-title">Cargo</label>
                  <input
                    id="employee-edit-job-title"
                    value={editForm.job_title}
                    onChange={(event) => setEditForm({ ...editForm, job_title: event.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="employee-edit-department">Área</label>
                  <input
                    id="employee-edit-department"
                    value={editForm.department}
                    onChange={(event) => setEditForm({ ...editForm, department: event.target.value })}
                  />
                </div>
              </div>

              <div className="employee-form-grid">
                <div className="form-group">
                  <label htmlFor="employee-edit-role">Rol</label>
                  <select
                    id="employee-edit-role"
                    value={editForm.role}
                    onChange={(event) => setEditForm({ ...editForm, role: event.target.value })}
                  >
                    <option value="EMPLOYEE">Empleado</option>
                    <option value="ADMIN">Administrador</option>
                    {isSuperAdmin && <option value="SUPER_ADMIN">Super administrador</option>}
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="employee-edit-onboarding">Onboarding ASIATI</label>
                  <select
                    id="employee-edit-onboarding"
                    value={editForm.onboarding_required ? "REQUIRED" : "NOT_REQUIRED"}
                    onChange={(event) => setEditForm({
                      ...editForm,
                      onboarding_required: event.target.value === "REQUIRED",
                    })}
                  >
                    <option value="REQUIRED">Requerido</option>
                    <option value="NOT_REQUIRED">No requerido</option>
                  </select>
                  <small>
                    El progreso se calcula automáticamente a partir de las actividades completadas.
                  </small>
                </div>
              </div>

              <div className="form-actions">
                <button className="btn btn-secondary" type="button" onClick={closeEmployeeEditor}>
                  Cancelar
                </button>
                <button className="btn btn-primary" type="submit" disabled={saving}>
                  {saving ? "Guardando…" : "Guardar cambios"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {onboardingTarget && (
        <div className="modal-overlay" role="presentation" onMouseDown={closeOnboardingDetail}>
          <section
            className="modal employee-onboarding-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="employee-onboarding-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Seguimiento de onboarding</span>
                <h2 id="employee-onboarding-modal-title">
                  {[onboardingTarget.first_name, onboardingTarget.last_name].filter(Boolean).join(" ") || onboardingTarget.email}
                </h2>
                <p>{onboardingTarget.onboarding?.course_title || "Onboarding ASIATI"}</p>
              </div>
              <button className="btn-close" type="button" aria-label="Cerrar detalle de onboarding" onClick={closeOnboardingDetail}>×</button>
            </div>

            {onboardingDetailLoading ? (
              <LoadingState label="Cargando progreso…" compact />
            ) : onboardingDetailError ? (
              <FeedbackMessage title="El detalle de onboarding no está disponible">{onboardingDetailError}</FeedbackMessage>
            ) : onboardingDetail?.course ? (
              <div className="employee-onboarding-detail">
                <div className="employee-onboarding-summary">
                  <div>
                    <span>Progreso total</span>
                    <strong>{Number(onboardingDetail.course.progress_percent || 0)}%</strong>
                  </div>
                  <div>
                    <span>Actividades</span>
                    <strong>
                      {onboardingDetail.course.completed_lessons || 0}/{onboardingDetail.course.lesson_count || 0}
                    </strong>
                  </div>
                  <div>
                    <span>Estado</span>
                    <strong>{onboardingTarget.onboarding_status === "COMPLETED" ? "Completado" : onboardingTarget.onboarding_status === "IN_PROGRESS" ? "En progreso" : "Pendiente"}</strong>
                  </div>
                </div>

                <div className="employee-onboarding-module-list">
                  {(onboardingDetail.course.modules || []).map((module) => (
                    <article className="employee-onboarding-module" key={module.id}>
                      <div>
                        <strong>{module.title}</strong>
                        <small>{module.completed_lessons || 0}/{module.lesson_count || 0} actividades</small>
                      </div>
                      <span>{Number(module.progress_percent || 0)}%</span>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      )}

      {formOpen && (
        <div className="modal-overlay" role="presentation" onMouseDown={() => setFormOpen(false)}>
          <section className="modal employee-modal" role="dialog" aria-modal="true" aria-labelledby="employee-modal-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <span className="eyebrow">Nuevo acceso</span>
                <h2 id="employee-modal-title">Crear empleado</h2>
                <p>La cuenta se creará en Cognito y recibirá la invitación de acceso por correo.</p>
              </div>
              <button className="btn-close" type="button" aria-label="Cerrar" onClick={() => setFormOpen(false)}>×</button>
            </div>

            <form className="employee-form" onSubmit={createEmployee}>
              <div className="employee-form-grid">
                <div className="form-group">
                  <label htmlFor="employee-first-name">Nombre</label>
                  <input id="employee-first-name" value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} required />
                </div>
                <div className="form-group">
                  <label htmlFor="employee-last-name">Apellido</label>
                  <input id="employee-last-name" value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} required />
                </div>
              </div>
              <div className="form-group">
                <label htmlFor="employee-email">Correo corporativo</label>
                <input id="employee-email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
              </div>
              <div className="employee-form-grid">
                <div className="form-group">
                  <label htmlFor="employee-job-title">Cargo</label>
                  <input id="employee-job-title" value={form.job_title} onChange={(event) => setForm({ ...form, job_title: event.target.value })} />
                </div>
                <div className="form-group">
                  <label htmlFor="employee-department">Área</label>
                  <input id="employee-department" value={form.department} onChange={(event) => setForm({ ...form, department: event.target.value })} />
                </div>
              </div>
              <div className="form-group">
                <label htmlFor="employee-hire-date">Fecha de ingreso</label>
                <input
                  id="employee-hire-date"
                  type="date"
                  value={form.hire_date}
                  onChange={(event) => setForm({ ...form, hire_date: event.target.value })}
                />
              </div>
              {isSuperAdmin && (
                <div className="form-group">
                  <label htmlFor="employee-role">Rol inicial</label>
                  <select id="employee-role" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
                    <option value="EMPLOYEE">Empleado</option>
                    <option value="ADMIN">Administrador</option>
                    <option value="SUPER_ADMIN">Super administrador</option>
                  </select>
                </div>
              )}
              <div className="form-actions">
                <button className="btn btn-secondary" type="button" onClick={() => setFormOpen(false)}>Cancelar</button>
                <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? "Creando…" : "Crear empleado"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

export default Employees;
