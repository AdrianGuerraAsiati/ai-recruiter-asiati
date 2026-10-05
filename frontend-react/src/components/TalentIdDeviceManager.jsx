// eslint-disable-next-line no-unused-vars
import React from "react";
import { useMemo, useState } from "react";

import api from "../api/client";
import { EmptyState } from "./ui/StatePanel";
import { getApiErrorMessage } from "../utils/errors";


function CredentialField({ label, value, copyLabel, onCopy }) {
  return (
    <div className="talent-id-credential-field">
      <div>
        <span>{label}</span>
        <code>{value}</code>
      </div>
      <button
        className="btn btn-secondary talent-id-copy-button"
        type="button"
        onClick={() => onCopy(value, label)}
      >
        {copyLabel}
      </button>
    </div>
  );
}


function formatActivity(value) {
  if (!value) return "Aún sin conexión";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Con actividad";
  return `Última conexión · ${date.toLocaleString("es-CO")}`;
}


function TalentIdDeviceManager({
  sites,
  devices,
  onRefresh,
  onError,
  onFeedback,
}) {
  const [saving, setSaving] = useState("");
  const [deviceForm, setDeviceForm] = useState({ site_id: "", name: "Recepción" });
  const [credential, setCredential] = useState(null);
  const [editingId, setEditingId] = useState("");
  const [editForm, setEditForm] = useState({ site_id: "", name: "" });
  const [confirmAction, setConfirmAction] = useState(null);

  const activeSites = useMemo(
    () => sites.filter((site) => site.active !== false),
    [sites],
  );
  const selectedSiteId =
    deviceForm.site_id || (activeSites.length === 1 ? activeSites[0].id : "");

  function siteName(siteId) {
    return sites.find((site) => site.id === siteId)?.name || "Sede no disponible";
  }

  async function refresh() {
    await onRefresh?.({ silent: true });
  }

  async function copyValue(value, label) {
    try {
      await navigator.clipboard.writeText(value);
      onFeedback?.(`${label} copiado al portapapeles.`);
    } catch {
      onFeedback?.(`No se pudo copiar ${label.toLowerCase()}. Selecciónalo y cópialo manualmente.`);
    }
  }

  async function provisionDevice(event) {
    event.preventDefault();
    if (!selectedSiteId) {
      onError?.("Selecciona una sede para el kiosco.");
      return;
    }

    setSaving("create");
    setCredential(null);
    onError?.("");
    onFeedback?.("");
    try {
      const { data } = await api.post("/talent-id/devices", {
        site_id: selectedSiteId,
        name: deviceForm.name.trim(),
      });
      setCredential(data);
      setDeviceForm((current) => ({ ...current, name: "Recepción" }));
      onFeedback?.("Credenciales generadas. Cárgalas en la tablet antes de cerrar esta vista.");
      await refresh();
    } catch (err) {
      onError?.(getApiErrorMessage(err, {
        action: "provisionar el kiosco",
        resource: "Talent ID",
        fallback: "No se pudo generar el acceso del kiosco. Verifica la sede y vuelve a intentarlo.",
      }));
    } finally {
      setSaving("");
    }
  }

  function beginEdit(device) {
    setConfirmAction(null);
    setEditingId(device.id);
    setEditForm({
      site_id: device.site_id,
      name: device.name,
    });
  }

  async function saveDevice(event) {
    event.preventDefault();
    const device = devices.find((item) => item.id === editingId);
    if (!device) return;

    setSaving(`edit:${device.id}`);
    onError?.("");
    try {
      await api.patch(`/talent-id/devices/${device.id}`, {
        site_id: editForm.site_id,
        name: editForm.name.trim(),
      });
      setEditingId("");
      onFeedback?.("Dispositivo actualizado.");
      await refresh();
    } catch (err) {
      onError?.(getApiErrorMessage(err, {
        action: "actualizar el kiosco",
        resource: "Talent ID",
        fallback: "No se pudo actualizar el dispositivo.",
      }));
    } finally {
      setSaving("");
    }
  }

  async function rotateSecret(device) {
    setSaving(`rotate:${device.id}`);
    setConfirmAction(null);
    onError?.("");
    try {
      const { data } = await api.post(`/talent-id/devices/${device.id}/rotate-secret`);
      setCredential(data);
      onFeedback?.("Se generó un nuevo Device Secret. El anterior dejó de ser válido.");
      await refresh();
    } catch (err) {
      onError?.(getApiErrorMessage(err, {
        action: "regenerar el secreto",
        resource: "Talent ID",
        fallback: "No se pudo regenerar el secreto del dispositivo.",
      }));
    } finally {
      setSaving("");
    }
  }

  async function revokeDevice(device) {
    setSaving(`delete:${device.id}`);
    setConfirmAction(null);
    onError?.("");
    try {
      await api.delete(`/talent-id/devices/${device.id}`);
      if (credential?.device?.id === device.id) setCredential(null);
      onFeedback?.("Acceso del dispositivo eliminado. Sus credenciales anteriores ya no funcionan.");
      await refresh();
    } catch (err) {
      onError?.(getApiErrorMessage(err, {
        action: "eliminar el acceso del kiosco",
        resource: "Talent ID",
        fallback: "No se pudo eliminar el acceso del dispositivo.",
      }));
    } finally {
      setSaving("");
    }
  }

  async function reactivateDevice(device) {
    setSaving(`reactivate:${device.id}`);
    onError?.("");
    try {
      await api.patch(`/talent-id/devices/${device.id}`, { active: true });
      const { data } = await api.post(`/talent-id/devices/${device.id}/rotate-secret`);
      setCredential(data);
      onFeedback?.("Dispositivo reactivado. Usa el nuevo secreto mostrado abajo.");
      await refresh();
    } catch (err) {
      onError?.(getApiErrorMessage(err, {
        action: "reactivar el kiosco",
        resource: "Talent ID",
        fallback: "No se pudo reactivar el dispositivo.",
      }));
    } finally {
      setSaving("");
    }
  }

  return (
    <section className="panel talent-id-admin-card talent-id-device-card">
      <div className="talent-id-device-heading">
        <div>
          <span className="eyebrow">4 · Dispositivos</span>
          <h2>Credenciales de kioscos</h2>
          <p className="muted">
            Crea, consulta, edita y revoca el acceso de las tablets. Los secretos nunca se almacenan en texto plano.
          </p>
        </div>
        <span className="talent-id-device-count">{devices.length} registrados</span>
      </div>

      <form className="talent-id-admin-form talent-id-device-create" onSubmit={provisionDevice}>
        <div className="talent-id-form-heading">
          <div>
            <strong>Nuevo kiosco</strong>
            <span>Genera un Device ID y un Device Secret de un solo uso.</span>
          </div>
        </div>
        <div className="talent-id-device-form-grid">
          <div className="form-group">
            <label htmlFor="talent-device-site">Sede del kiosco</label>
            <select
              id="talent-device-site"
              value={selectedSiteId}
              onChange={(event) => setDeviceForm({ ...deviceForm, site_id: event.target.value })}
              required
              disabled={activeSites.length === 0}
            >
              <option value="">Selecciona sede</option>
              {activeSites.map((site) => (
                <option key={site.id} value={site.id}>{site.name}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="talent-device-name">Nombre del dispositivo</label>
            <input
              id="talent-device-name"
              value={deviceForm.name}
              onChange={(event) => setDeviceForm({ ...deviceForm, name: event.target.value })}
              placeholder="Ej. Recepción principal"
              required
            />
          </div>
        </div>
        <button
          className="btn btn-primary"
          type="submit"
          disabled={saving === "create" || activeSites.length === 0}
        >
          {saving === "create" ? "Generando…" : "Generar credenciales"}
        </button>
      </form>

      {credential?.device_secret && (
        <div className="talent-id-device-secret" role="alert">
          <div className="talent-id-secret-heading">
            <div>
              <strong>Credenciales listas</strong>
              <span>Se muestran una sola vez. Guarda ambas antes de salir.</span>
            </div>
            <span className="talent-id-one-time-badge">Una sola vez</span>
          </div>

          <div className="talent-id-credentials-grid">
            <CredentialField
              label="Device ID"
              value={credential.device?.id || ""}
              copyLabel="Copiar ID"
              onCopy={copyValue}
            />
            <CredentialField
              label="Device Secret"
              value={credential.device_secret}
              copyLabel="Copiar secret"
              onCopy={copyValue}
            />
          </div>

          <p className="talent-id-secret-note">
            Si pierdes el Device Secret, no se puede consultar de nuevo: debes regenerarlo desde el dispositivo.
          </p>
        </div>
      )}

      <div className="talent-id-device-list-heading">
        <div>
          <h3>Dispositivos registrados</h3>
          <p>Administra nombre, sede, estado y credenciales de cada tablet.</p>
        </div>
      </div>

      <div className="talent-id-device-grid">
        {devices.length === 0 ? (
          <EmptyState
            compact
            title="No hay kioscos provisionados"
            description="Crea el primer dispositivo para comenzar las pruebas."
          />
        ) : devices.map((device) => {
          const editing = editingId === device.id;
          const confirming = confirmAction?.deviceId === device.id;
          return (
            <article key={device.id} className={`talent-id-device-item ${device.active ? "" : "is-revoked"}`}>
              <div className="talent-id-device-item-top">
                <div className="talent-id-device-identity">
                  <span className="talent-id-device-icon" aria-hidden="true">ID</span>
                  <div>
                    <strong>{device.name}</strong>
                    <small>{siteName(device.site_id)} · {formatActivity(device.last_seen_at)}</small>
                  </div>
                </div>
                <span className={`status-pill ${device.active ? "" : "status-disabled"}`}>
                  <i /> {device.active ? "Activo" : "Revocado"}
                </span>
              </div>

              <div className="talent-id-device-id-row">
                <div>
                  <span>Device ID</span>
                  <code>{device.id}</code>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary talent-id-copy-button"
                  onClick={() => copyValue(device.id, "Device ID")}
                >
                  Copiar ID
                </button>
              </div>

              {editing ? (
                <form className="talent-id-device-edit" onSubmit={saveDevice}>
                  <div className="form-group">
                    <label htmlFor={`device-name-${device.id}`}>Nombre</label>
                    <input
                      id={`device-name-${device.id}`}
                      value={editForm.name}
                      onChange={(event) => setEditForm({ ...editForm, name: event.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor={`device-site-${device.id}`}>Sede</label>
                    <select
                      id={`device-site-${device.id}`}
                      value={editForm.site_id}
                      onChange={(event) => setEditForm({ ...editForm, site_id: event.target.value })}
                      required
                    >
                      {activeSites.map((site) => (
                        <option key={site.id} value={site.id}>{site.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="talent-id-device-edit-actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setEditingId("")}
                    >
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={saving === `edit:${device.id}`}
                    >
                      {saving === `edit:${device.id}` ? "Guardando…" : "Guardar cambios"}
                    </button>
                  </div>
                </form>
              ) : (
                <div className="talent-id-device-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => beginEdit(device)}>
                    Editar
                  </button>
                  {device.active ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setConfirmAction({ type: "rotate", deviceId: device.id })}
                      >
                        Regenerar secret
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => setConfirmAction({ type: "delete", deviceId: device.id })}
                      >
                        Eliminar acceso
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => reactivateDevice(device)}
                      disabled={saving === `reactivate:${device.id}`}
                    >
                      {saving === `reactivate:${device.id}` ? "Reactivando…" : "Reactivar y generar secret"}
                    </button>
                  )}
                </div>
              )}

              {confirming && (
                <div className="talent-id-device-confirm">
                  {confirmAction.type === "rotate" ? (
                    <p>El secret actual dejará de funcionar inmediatamente. ¿Generar uno nuevo?</p>
                  ) : (
                    <p>Se revocará este kiosco y sus credenciales actuales dejarán de funcionar. ¿Continuar?</p>
                  )}
                  <div>
                    <button type="button" className="btn btn-secondary" onClick={() => setConfirmAction(null)}>
                      Cancelar
                    </button>
                    <button
                      type="button"
                      className={`btn ${confirmAction.type === "delete" ? "btn-danger" : "btn-primary"}`}
                      onClick={() => (
                        confirmAction.type === "delete"
                          ? revokeDevice(device)
                          : rotateSecret(device)
                      )}
                    >
                      {confirmAction.type === "delete" ? "Sí, eliminar acceso" : "Sí, regenerar"}
                    </button>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default TalentIdDeviceManager;
