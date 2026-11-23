import { useCallback, useEffect, useState } from "react";

import api from "../api/client";
import EmployeeCredentialsModal from "../components/EmployeeCredentialsModal";
import PageHeader from "../components/ui/PageHeader";
import { EmptyState, FeedbackMessage, LoadingState } from "../components/ui/StatePanel";
import { getApiErrorMessage } from "../utils/errors";
import { useNotice } from "../context/noticeStore";
import { suggestUsername } from "../utils/username";

function displayName(employee) {
  return [employee.first_name, employee.last_name].filter(Boolean).join(" ")
    || employee.email
    || "Empleado";
}

function needsCredentials(employee) {
  return !employee.username || !employee.access_provisioned;
}

export default function AccessManagement() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [usernameTarget, setUsernameTarget] = useState(null);
  const [usernameValue, setUsernameValue] = useState("");
  const [usernameError, setUsernameError] = useState("");
  const [credentialResult, setCredentialResult] = useState(null);
  const [generateTarget, setGenerateTarget] = useState(null);
  const [generateUsername, setGenerateUsername] = useState("");
  const [generateError, setGenerateError] = useState("");
  const { notify } = useNotice();

  function openGenerator(employee) {
    setGenerateTarget(employee);
    setGenerateUsername(employee.username || suggestUsername(employee));
    setGenerateError("");
  }

  async function generateCredentials(event) {
    event.preventDefault();
    if (!generateTarget) return;
    const target = generateTarget;
    setBusyId(target.id);
    setGenerateError("");
    try {
      const { data } = await api.post(
        "/employees/" + encodeURIComponent(target.id) + "/credentials/generate",
        { username: generateUsername },
      );
      setGenerateTarget(null);
      setCredentialResult({
        employeeName: displayName(target),
        credentials: data?.credentials,
      });
      await loadEmployees();
    } catch (err) {
      setGenerateError(getApiErrorMessage(err, {
        action: "generar las credenciales",
        resource: "acceso",
        fallback: "No fue posible generar las credenciales.",
      }));
    } finally {
      setBusyId("");
    }
  }

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get("/employees");
      setEmployees(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar los accesos",
        resource: "usuarios",
        fallback: "No se pudo cargar la administración de usuarios.",
      }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadEmployees();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadEmployees]);

  function openUsernameEditor(employee) {
    setUsernameTarget(employee);
    setUsernameValue(employee.username || "");
    setUsernameError("");
  }

  async function saveUsername(event) {
    event.preventDefault();
    if (!usernameTarget) return;
    setBusyId(usernameTarget.id);
    setUsernameError("");
    try {
      await api.put("/employees/" + usernameTarget.id + "/credentials/username", {
        username: usernameValue,
      });
      setUsernameTarget(null);
      await loadEmployees();
    } catch (err) {
      setUsernameError(getApiErrorMessage(err, {
        action: "cambiar el usuario",
        resource: "acceso",
        fallback: "No fue posible cambiar el usuario.",
      }));
    } finally {
      setBusyId("");
    }
  }

  async function resetPassword(employee) {
    if (!window.confirm("¿Generar una nueva contraseña temporal para " + displayName(employee) + "?")) {
      return;
    }
    setBusyId(employee.id);
    setError("");
    try {
      const { data } = await api.post(
        "/employees/" + employee.id + "/credentials/reset-password",
      );
      setCredentialResult({
        employeeName: displayName(employee),
        credentials: data?.credentials,
      });
      await loadEmployees();
    } catch (err) {
      const message = getApiErrorMessage(err, {
        action: "restablecer la contraseña",
        resource: "acceso",
        fallback: "No fue posible generar una nueva contraseña temporal.",
      });
      setError(message);
      // El aviso de la página queda arriba y fuera de vista en listas largas.
      notify({ tone: "error", title: "No se generó la contraseña", message });
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="page access-management-page">
      <PageHeader
        eyebrow="Administración"
        title="Usuarios y accesos"
        description="Administra los usuarios de Talent y genera contraseñas temporales. Las contraseñas actuales nunca se almacenan ni se muestran."
      />

      {error && <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>}

      <section className="panel employee-list-panel">
        <div className="employee-toolbar">
          <div>
            <span className="eyebrow">Credenciales</span>
            <h2>Accesos del equipo</h2>
          </div>
        </div>

        {loading ? (
          <LoadingState label="Cargando usuarios…" compact />
        ) : employees.length === 0 ? (
          <EmptyState
            compact
            icon="employee"
            title="No hay empleados"
            description="Los accesos aparecerán cuando se creen empleados."
          />
        ) : (
          <div className="employee-table-wrap">
            <table className="employee-table">
              <thead>
                <tr>
                  <th>Empleado</th>
                  <th>Usuario</th>
                  <th>Rol</th>
                  <th>Estado</th>
                  <th aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => (
                  <tr key={employee.id}>
                    <td>
                      <div className="employee-person">
                        <span className="employee-avatar" aria-hidden="true">
                          {(employee.first_name?.[0] || employee.email?.[0] || "?").toUpperCase()}
                        </span>
                        <div>
                          <strong>{displayName(employee)}</strong>
                          <small>{employee.email}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <strong>{employee.username || "Sin usuario asignado"}</strong>
                    </td>
                    <td>{employee.roles?.includes("ADMIN") ? "Administrador" : "Empleado"}</td>
                    <td>
                      <span className={"status-pill " + (employee.status === "ACTIVE" ? "" : "status-disabled")}>
                        <i /> {employee.status === "ACTIVE" ? "Activo" : "Deshabilitado"}
                      </span>
                    </td>
                    <td>
                      <div className="ui-actions">
                        <button
                          className="btn btn-ghost btn-sm"
                          type="button"
                          disabled={busyId === employee.id}
                          onClick={() => openUsernameEditor(employee)}
                        >
                          Editar usuario
                        </button>
                        {needsCredentials(employee) ? (
                          <button
                            className="btn btn-primary btn-sm"
                            type="button"
                            disabled={busyId === employee.id || !employee.email}
                            title={employee.email ? undefined : "El perfil no tiene correo"}
                            onClick={() => openGenerator(employee)}
                          >
                            {busyId === employee.id ? "Procesando…" : "Generar credenciales"}
                          </button>
                        ) : (
                          <button
                            className="btn btn-secondary btn-sm"
                            type="button"
                            disabled={busyId === employee.id}
                            onClick={() => resetPassword(employee)}
                          >
                            {busyId === employee.id ? "Procesando…" : "Nueva contraseña"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {usernameTarget && (
        <div className="modal-overlay" role="presentation" onMouseDown={() => setUsernameTarget(null)}>
          <section
            className="modal employee-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="access-username-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Credencial</span>
                <h2 id="access-username-title">Cambiar usuario</h2>
                <p>{displayName(usernameTarget)}</p>
              </div>
              <button className="btn-close" type="button" onClick={() => setUsernameTarget(null)}>×</button>
            </div>
            {usernameError && <FeedbackMessage title="No se cambió el usuario">{usernameError}</FeedbackMessage>}
            <form className="employee-form" onSubmit={saveUsername}>
              <div className="form-group">
                <label htmlFor="access-username">Usuario de Talent</label>
                <input
                  id="access-username"
                  value={usernameValue}
                  onChange={(event) => setUsernameValue(event.target.value.toLowerCase())}
                  minLength={3}
                  maxLength={40}
                  autoComplete="off"
                  required
                />
                <small>El usuario anterior dejará de funcionar inmediatamente.</small>
              </div>
              <div className="form-actions">
                <button className="btn btn-secondary" type="button" onClick={() => setUsernameTarget(null)}>
                  Cancelar
                </button>
                <button className="btn btn-primary" type="submit" disabled={busyId === usernameTarget.id}>
                  {busyId === usernameTarget.id ? "Guardando…" : "Guardar usuario"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {generateTarget && (
        <div className="modal-overlay" role="presentation" onMouseDown={() => setGenerateTarget(null)}>
          <section
            className="modal employee-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="access-generate-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">Credenciales</span>
                <h2 id="access-generate-title">Generar credenciales</h2>
                <p>{displayName(generateTarget)}</p>
                {generateTarget.email && <small>{generateTarget.email}</small>}
              </div>
              <button className="btn-close" type="button" aria-label="Cerrar" onClick={() => setGenerateTarget(null)}>×</button>
            </div>
            {generateError && <FeedbackMessage title="No se generaron las credenciales">{generateError}</FeedbackMessage>}
            <form className="employee-form" onSubmit={generateCredentials}>
              <div className="form-group">
                <label htmlFor="access-generate-username">Usuario de Talent</label>
                <input
                  id="access-generate-username"
                  value={generateUsername}
                  onChange={(event) => setGenerateUsername(event.target.value.toLowerCase())}
                  minLength={3}
                  maxLength={40}
                  autoComplete="off"
                  required
                />
                <small>Se creará el acceso y una contraseña temporal que la persona deberá cambiar al ingresar.</small>
              </div>
              <div className="form-actions">
                <button className="btn btn-secondary" type="button" onClick={() => setGenerateTarget(null)}>
                  Cancelar
                </button>
                <button className="btn btn-primary" type="submit" disabled={busyId === generateTarget.id}>
                  {busyId === generateTarget.id ? "Generando." : "Generar credenciales"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      <EmployeeCredentialsModal
        open={Boolean(credentialResult?.credentials)}
        employeeName={credentialResult?.employeeName}
        credentials={credentialResult?.credentials}
        onClose={() => setCredentialResult(null)}
      />
    </div>
  );
}
