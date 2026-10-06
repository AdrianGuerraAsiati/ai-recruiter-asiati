// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import {
  EmptyState,
  FeedbackMessage,
  LoadingState,
  MetricCard,
} from "../components/ui/StatePanel";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../utils/errors";
import "../attendance.css";


function isoDate(value) {
  return value.toISOString().slice(0, 10);
}


function defaultRange() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  return {
    start_date: isoDate(start),
    end_date: isoDate(end),
  };
}


function employeeLabel(employee) {
  const name = [employee?.first_name, employee?.last_name].filter(Boolean).join(" ");
  return name
    ? `${name} · ${employee.email || ""}`
    : employee?.email || "Empleado";
}


function timeLabel(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
  });
}


function durationLabel(minutes) {
  if (minutes === null || minutes === undefined) return "—";
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (!hours) return `${rest} min`;
  return `${hours} h ${String(rest).padStart(2, "0")} min`;
}


function statusLabel(status) {
  if (status === "LATE") return "Llegada tarde";
  if (status === "INCOMPLETE") return "Marcación incompleta";
  return "Completa";
}


function methodLabel(method) {
  if (method === "REPORT") return "Reporte biométrico";
  if (method === "MANUAL") return "Ajuste histórico";
  if (method) return "Registro histórico";
  return "";
}


function unmatchedReason(reason) {
  return {
    NO_MATCH: "No coincide con un empleado activo",
    AMBIGUOUS_NAME: "Hay más de un empleado con ese nombre",
    ATTENDANCE_NOT_ENABLED: "Asistencia no habilitada para el empleado",
    SITE_MISMATCH: "El empleado está asignado a otra sede",
  }[reason] || "No se pudo asociar";
}


function Attendance() {
  const { principal, hasPermission } = useSession();
  const canReadAll = (
    hasPermission("talent_id.attendance.read_all")
    || hasPermission("talent_id.manage")
  );
  const canImportReports = hasPermission("talent_id.manage");

  const [range, setRange] = useState(() => defaultRange());
  const [employeeId, setEmployeeId] = useState("");
  const [employees, setEmployees] = useState([]);
  const [sites, setSites] = useState([]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [reportFile, setReportFile] = useState(null);
  const [reportSiteId, setReportSiteId] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  useEffect(() => {
    if (!canReadAll) return undefined;

    let cancelled = false;
    Promise.all([
      api.get("/employees", { params: { status: "ACTIVE" } }),
      api.get("/talent-id/sites"),
    ])
      .then(([employeesResponse, sitesResponse]) => {
        if (cancelled) return;
        const loadedEmployees = employeesResponse.data?.items || [];
        const loadedSites = (sitesResponse.data?.items || []).filter((site) => site.active !== false);
        setEmployees(
          loadedEmployees
            .slice()
            .sort((a, b) => employeeLabel(a).localeCompare(employeeLabel(b), "es", { sensitivity: "base" })),
        );
        setSites(loadedSites);
        setReportSiteId((current) => current || (loadedSites.length === 1 ? loadedSites[0].id : ""));
      })
      .catch(() => {
        if (!cancelled) {
          setEmployees([]);
          setSites([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [canReadAll]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {
        start_date: range.start_date,
        end_date: range.end_date,
      };
      if (canReadAll && employeeId) params.employee_id = employeeId;

      const { data } = await api.get("/talent-id/attendance/report", { params });
      setReport(data || null);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar el reporte de asistencia",
        resource: "asistencia",
        fallback: "No se pudo consultar la asistencia. Revisa el rango de fechas y vuelve a intentarlo.",
      }));
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [canReadAll, employeeId, range.end_date, range.start_date]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadReport();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadReport]);

  async function uploadBiometricReport(event) {
    event.preventDefault();
    if (!reportFile) {
      setError("Selecciona el archivo .xls exportado por el reloj biométrico.");
      return;
    }
    if (!reportSiteId) {
      setError("Selecciona la sede a la que corresponde el reporte.");
      return;
    }

    setImporting(true);
    setError("");
    setImportResult(null);
    try {
      const body = new FormData();
      body.append("report", reportFile);
      body.append("site_id", reportSiteId);
      const { data } = await api.post("/talent-id/attendance/import-report", body);
      setImportResult(data || null);
      setReportFile(null);

      const fileInput = document.getElementById("attendance-report-file");
      if (fileInput) fileInput.value = "";

      if (data?.date_range?.from && data?.date_range?.to) {
        setRange({
          start_date: String(data.date_range.from).slice(0, 10),
          end_date: String(data.date_range.to).slice(0, 10),
        });
      } else {
        await loadReport();
      }
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "importar el reporte biométrico",
        resource: "asistencia",
        fallback: "No fue posible leer el reporte. Verifica que sea el .xls original exportado por el equipo.",
      }));
    } finally {
      setImporting(false);
    }
  }

  const summary = report?.summary || {};
  const rows = report?.rows || [];
  const title = canReadAll ? "Asistencia del equipo" : "Mi asistencia";
  const ownName = [
    principal?.profile?.first_name,
    principal?.profile?.last_name,
  ].filter(Boolean).join(" ");

  const rateDetail = summary.check_ins
    ? `${summary.late_arrivals || 0} llegadas tarde`
    : "Sin entradas en el período";

  const tableTitle = useMemo(() => {
    if (!canReadAll) return ownName ? `Historial de ${ownName}` : "Mi historial";
    if (!employeeId) return "Historial de todos los empleados";
    const employee = employees.find((item) => item.id === employeeId);
    return employee ? `Historial de ${employeeLabel(employee)}` : "Historial filtrado";
  }, [canReadAll, employeeId, employees, ownName]);

  return (
    <div className="page attendance-page">
      <PageHeader
        eyebrow="Asistencia · Reportes biométricos"
        title={title}
        description={
          canReadAll
            ? "Carga los reportes exportados por los equipos de huella y consulta entradas, salidas, puntualidad y jornadas."
            : "Consulta tus entradas, salidas y puntualidad procesadas desde los reportes biométricos de la empresa."
        }
        actions={(
          <>
            {canImportReports && (
              <Link className="btn btn-secondary" to="/attendance/settings">
                Configurar sedes y horarios
              </Link>
            )}
            <button className="btn btn-secondary" type="button" onClick={loadReport} disabled={loading}>
              Actualizar
            </button>
          </>
        )}
        className="split-header"
      />

      {canImportReports && (
        <section className="panel attendance-import" aria-label="Importar reporte biométrico">
          <div className="attendance-import-heading">
            <div>
              <span className="eyebrow">Única fuente de asistencia</span>
              <h2>Cargar reporte del reloj biométrico</h2>
              <p>
                Talent acepta el archivo <b>.xls</b> original con las columnas ID de usuario, Nombre, Fecha/Hora,
                Dispositivo Nro., Registro y Departamento.
              </p>
            </div>
            <span className="attendance-import-badge">Huelleros</span>
          </div>

          <form className="attendance-import-form" onSubmit={uploadBiometricReport}>
            <div className="form-group">
              <label htmlFor="attendance-report-site">Sede del reporte</label>
              <select
                id="attendance-report-site"
                value={reportSiteId}
                onChange={(event) => setReportSiteId(event.target.value)}
                required
              >
                <option value="">Selecciona sede</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}{site.code ? ` · ${site.code}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group attendance-import-file">
              <label htmlFor="attendance-report-file">Reporte .xls</label>
              <input
                id="attendance-report-file"
                type="file"
                accept=".xls,application/vnd.ms-excel"
                onChange={(event) => setReportFile(event.target.files?.[0] || null)}
                required
              />
            </div>

            <button className="btn btn-primary" type="submit" disabled={importing || sites.length === 0}>
              {importing ? "Procesando reporte…" : "Cargar reporte"}
            </button>
          </form>

          <div className="attendance-import-help">
            <strong>Cómo se interpreta</strong>
            <span>
              Registro <b>0</b> = entrada y <b>1</b> = salida. Otros códigos no se inventan: se omiten y aparecen
              en el resumen para revisión. Repetir el mismo archivo no duplica marcaciones.
            </span>
          </div>

          {importResult && (
            <div className="attendance-import-result" role="status">
              <div className="attendance-import-result-heading">
                <div>
                  <span className="eyebrow">Importación completada</span>
                  <h3>{importResult.filename}</h3>
                  <p>
                    {importResult.site_name} · {String(importResult.date_range?.from || "").slice(0, 10)}
                    {" a "}{String(importResult.date_range?.to || "").slice(0, 10)}
                  </p>
                </div>
                <strong>{importResult.imported_events || 0} nuevas</strong>
              </div>

              <div className="attendance-import-stats">
                <div><span>Filas leídas</span><strong>{importResult.rows_total || 0}</strong></div>
                <div><span>Personas fuente</span><strong>{importResult.source_users || 0}</strong></div>
                <div><span>Empleados asociados</span><strong>{importResult.matched_employees || 0}</strong></div>
                <div><span>Duplicadas</span><strong>{importResult.duplicate_events || 0}</strong></div>
                <div><span>Códigos omitidos</span><strong>{importResult.unsupported_rows || 0}</strong></div>
                <div>
                  <span>Sin asociar/configurar</span>
                  <strong>
                    {(importResult.unmatched_rows || 0)
                      + (importResult.ambiguous_rows || 0)
                      + (importResult.attendance_not_enabled_rows || 0)
                      + (importResult.site_mismatch_rows || 0)}
                  </strong>
                </div>
              </div>

              {Object.keys(importResult.unsupported_codes || {}).length > 0 && (
                <p className="attendance-import-warning">
                  Códigos de Registro no interpretados: {Object.entries(importResult.unsupported_codes)
                    .map(([code, count]) => `${code} (${count})`)
                    .join(", ")}.
                </p>
              )}

              {(importResult.unmatched_people || []).length > 0 && (
                <details className="attendance-import-unmatched">
                  <summary>Ver personas que requieren revisión ({importResult.unmatched_people.length})</summary>
                  <div>
                    {importResult.unmatched_people.map((person) => (
                      <article key={`${person.device_user_id}-${person.name}`}>
                        <strong>{person.name}</strong>
                        <span>ID reloj {person.device_user_id || "—"} · {person.department || "Sin departamento"}</span>
                        <small>{unmatchedReason(person.reason)}</small>
                      </article>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </section>
      )}

      <section className="panel attendance-filters" aria-label="Filtros de asistencia">
        <div className="attendance-filter-grid">
          <div className="form-group">
            <label htmlFor="attendance-start">Desde</label>
            <input
              id="attendance-start"
              type="date"
              value={range.start_date}
              onChange={(event) => setRange({ ...range, start_date: event.target.value })}
            />
          </div>
          <div className="form-group">
            <label htmlFor="attendance-end">Hasta</label>
            <input
              id="attendance-end"
              type="date"
              value={range.end_date}
              onChange={(event) => setRange({ ...range, end_date: event.target.value })}
            />
          </div>
          {canReadAll && (
            <div className="form-group attendance-employee-filter">
              <label htmlFor="attendance-employee">Empleado</label>
              <select
                id="attendance-employee"
                value={employeeId}
                onChange={(event) => setEmployeeId(event.target.value)}
              >
                <option value="">Todos los empleados</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employeeLabel(employee)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <small>
          Puedes consultar hasta 93 días por vez. Las horas se interpretan con la zona horaria de la sede.
        </small>
      </section>

      {error && (
        <FeedbackMessage title="No se pudo completar la operación">{error}</FeedbackMessage>
      )}

      {loading ? (
        <LoadingState label="Calculando asistencia…" />
      ) : (
        <>
          <section className="metrics-grid attendance-metrics" aria-label="Resumen de asistencia">
            <MetricCard
              icon="calendar"
              label="Días con actividad"
              value={summary.days_with_activity || 0}
              detail={canReadAll ? `${summary.employees_with_activity || 0} empleados con marcaciones` : "Días con entrada o salida"}
              tone="blue"
            />
            <MetricCard
              icon="check"
              label="Puntualidad"
              value={`${Number(summary.on_time_rate || 0).toFixed(1)}%`}
              detail={rateDetail}
              tone="cyan"
            />
            <MetricCard
              icon="progress"
              label="Entradas / salidas"
              value={`${summary.check_ins || 0} / ${summary.check_outs || 0}`}
              detail={`${summary.incomplete_days || 0} jornadas incompletas`}
              tone="violet"
            />
            <MetricCard
              icon="calendar"
              label="Promedio trabajado"
              value={durationLabel(summary.average_worked_minutes)}
              detail="Calculado solo con jornadas completas"
              tone="neutral"
            />
            {canReadAll && (
              <MetricCard
                icon="check"
                label="Marcaciones importadas"
                value={summary.report_events || 0}
                detail="Eventos provenientes de reportes biométricos"
                tone="neutral"
              />
            )}
          </section>

          <section className="panel attendance-history">
            <div className="attendance-history-heading">
              <div>
                <span className="eyebrow">Detalle diario</span>
                <h2>{tableTitle}</h2>
                <p>
                  {report?.range
                    ? `${report.range.start_date} a ${report.range.end_date}`
                    : "Período seleccionado"}
                </p>
              </div>
              <span className="attendance-count">{rows.length} jornadas</span>
            </div>

            {rows.length === 0 ? (
              <EmptyState
                icon="calendar"
                title="No hay marcaciones en este período"
                description="Carga un reporte biométrico para incorporar entradas y salidas."
              />
            ) : (
              <div className="table-wrap attendance-table-wrap">
                <table className="attendance-table">
                  <thead>
                    <tr>
                      {canReadAll && <th>Empleado</th>}
                      <th>Fecha</th>
                      <th>Sede</th>
                      <th>Entrada</th>
                      <th>Salida</th>
                      <th>Jornada</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={`${row.employee_id}-${row.date}`}>
                        {canReadAll && (
                          <td>
                            <strong>{row.employee_name}</strong>
                            <small>{row.employee_email || ""}</small>
                          </td>
                        )}
                        <td>
                          <strong>{row.date}</strong>
                          <small>{row.schedule_name || "Sin horario"}</small>
                        </td>
                        <td>{row.site_name}</td>
                        <td>
                          <strong>{timeLabel(row.check_in)}</strong>
                          {row.check_in_method && <small>{methodLabel(row.check_in_method)}</small>}
                          {row.late_minutes > 0 && <small className="attendance-late">+{row.late_minutes} min</small>}
                        </td>
                        <td>
                          <strong>{timeLabel(row.check_out)}</strong>
                          {row.check_out_method && <small>{methodLabel(row.check_out_method)}</small>}
                        </td>
                        <td>{durationLabel(row.worked_minutes)}</td>
                        <td>
                          <span className={`attendance-status attendance-status-${String(row.status || "OK").toLowerCase()}`}>
                            {statusLabel(row.status)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default Attendance;
