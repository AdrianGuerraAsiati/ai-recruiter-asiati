// eslint-disable-next-line no-unused-vars
import React from "react";

import { useSession } from "../context/SessionContext";
import PageHeader from "../components/ui/PageHeader";
import BiometricConsentCard from "../components/BiometricConsentCard";
import MobileAttendanceCard from "../components/MobileAttendanceCard";
import EmployeeSelfServiceCard from "../components/EmployeeSelfServiceCard";
import "../employee-self-service.css";

function roleName(roles = []) {
  if (roles.includes("SUPER_ADMIN")) return "Dirección";
  if (roles.includes("ADMIN")) return "Administración";
  return "Empleado";
}

function formatDate(value) {
  if (!value) return "Por completar";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
}

function onboardingLabel(status) {
  return {
    PENDING: "Pendiente",
    IN_PROGRESS: "En progreso",
    COMPLETED: "Completado",
    NOT_REQUIRED: "No requerido",
  }[status] || "No requerido";
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function Profile() {
  const { principal } = useSession();
  const profile = principal?.profile || {};
  const email = principal?.email || "Correo no registrado";
  const hasName = Boolean(profile.first_name || profile.last_name);
  const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(" ") || email.split("@")[0];
  const role = roleName(principal?.roles);
  const onboarding = onboardingLabel(profile.onboarding_status);

  const details = [
    { label: "Cargo", value: profile.job_title || "Por completar" },
    { label: "Área", value: profile.department || "Por completar" },
    { label: "Fecha de ingreso", value: formatDate(profile.hire_date) },
  ];

  return (
    <div className="page profile-page">
      <PageHeader
        eyebrow="Cuenta personal"
        title="Mi perfil"
        description="Tu información de acceso y vinculación con ASIATI."
      />

      <section className="panel profile-card">
        <div className="profile-identity">
          <div className="profile-avatar" aria-hidden="true">{initials(fullName)}</div>
          <div className="profile-identity-copy">
            <div className="profile-badges">
              <span className="profile-role-badge">{role}</span>
              <span className="profile-active-badge">Cuenta activa</span>
            </div>
            <h2>{hasName ? fullName : "Perfil de ASIATI"}</h2>
            <p>{email}</p>
          </div>
        </div>

        <div className="profile-content-grid">
          <div className="profile-details">
            <div className="profile-section-heading">
              <span className="eyebrow">Información laboral</span>
              <p>Estos datos identifican tu rol dentro de la organización.</p>
            </div>
            <div className="profile-detail-grid">
              {details.map((item) => (
                <div className="profile-detail" key={item.label}>
                  <span>{item.label}</span>
                  <strong className={item.value === "Por completar" ? "is-empty" : ""}>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>

          <aside className="profile-onboarding-card">
            <span className="eyebrow">Onboarding</span>
            <strong>{onboarding}</strong>
            <p>
              {profile.onboarding_status === "COMPLETED"
                ? "Tu ruta de incorporación está completada."
                : profile.onboarding_status === "IN_PROGRESS"
                  ? "Continúa con los módulos pendientes de tu ruta."
                  : "Tu ruta de incorporación se habilitará cuando corresponda."}
            </p>
          </aside>
        </div>
      </section>

      <EmployeeSelfServiceCard />
      <BiometricConsentCard />
      <MobileAttendanceCard />
    </div>
  );
}

export default Profile;
