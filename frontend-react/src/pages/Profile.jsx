// eslint-disable-next-line no-unused-vars
import React from "react";

import { useSession } from "../context/SessionContext";


function roleName(roles = []) {
  if (roles.includes("SUPER_ADMIN")) return "Dirección";
  if (roles.includes("ADMIN")) return "Administración";
  return "Empleado";
}


function formatDate(value) {
  if (!value) return "No registrada";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("es-CO");
}


function onboardingLabel(status) {
  return {
    PENDING: "Pendiente",
    IN_PROGRESS: "En progreso",
    COMPLETED: "Completado",
    NOT_REQUIRED: "No requerido",
  }[status] || "No requerido";
}


function Profile() {
  const { principal } = useSession();
  const profile = principal?.profile || {};
  const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(" ")
    || principal?.email
    || "Usuario ASIATI";

  return (
    <div className="page profile-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Cuenta personal</span>
          <h1>Mi perfil</h1>
          <p>Consulta la información asociada a tu cuenta y tu acceso dentro de ASIATI.</p>
        </div>
      </header>

      <section className="panel">
        <div className="panel-heading">
          <div><span className="eyebrow">{roleName(principal?.roles)}</span><h2>{fullName}</h2></div>
        </div>
        <div className="onboarding-summary-grid">
          <div><span>Correo</span><strong>{principal?.email || "No registrado"}</strong></div>
          <div><span>Cargo</span><strong>{profile.job_title || "No registrado"}</strong></div>
          <div><span>Área</span><strong>{profile.department || "No registrada"}</strong></div>
          <div><span>Fecha de ingreso</span><strong>{formatDate(profile.hire_date)}</strong></div>
          <div><span>Onboarding</span><strong>{onboardingLabel(profile.onboarding_status)}</strong></div>
          <div><span>Estado de cuenta</span><strong>{profile.status === "ACTIVE" ? "Activa" : profile.status || "Sin estado"}</strong></div>
        </div>
      </section>
    </div>
  );
}

export default Profile;
