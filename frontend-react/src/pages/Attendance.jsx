// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

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


function Attendance() {
  const { principal, hasPermission } = useSession();
  const canReadAll = hasPermission("talent_id.attendance.read_all");
  const [range, setRange] = useState(() => defaultRange());
  const [employeeId, setEmployeeId] = useState("");
  const [employees, setEmployees] = useState([]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canReadAll) return undefined;

    let cancelled = false;
    api.get("/employees", { params: { status: "ACTIVE" } })
      .then(({ data }) => {
        if (cancelled) return;
        setEmployees(
          (data?.items || [])
            .slice()
            .sort((a, b) => employeeLabel(a).localeCompare(employeeLabel(b), "es", { sensitivity: "base" })),
        );
      })
      .catch(() => {
        if (!cancelled) setEmployees([]);
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
        resource: "Talent ID",
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
        eyebrow="Talent ID · Asistencia"
        title={title}
        description={
          canReadAll
            ? "Consulta entradas, salidas, puntualidad y jornadas registradas por Talent ID."
            : "Consulta tus propias entradas, salidas y puntualidad registradas por Talent ID."
        }
        actions={(
          <button className="btn btn-secondary" type="button" onClick={loadReport} disabled={loading}>
            Actualizar
          </button>
        )}
        className="split-header"
      />

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
          Puedes consultar hasta 93 días por vez. Las horas se muestran en tu zona horaria local.
        </small>
      </section>

      {error && (
        <FeedbackMessage title="No se pudo cargar la asistencia">{error}</FeedbackMessage>
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
                description="Cuando Talent ID registre entradas o salidas, aparecerán aquí."
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
                          {row.late_minutes > 0 && <small className="attendance-late">+{row.late_minutes} min</small>}
                        </td>
                        <td><strong>{timeLabel(row.check_out)}</strong></td>
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
