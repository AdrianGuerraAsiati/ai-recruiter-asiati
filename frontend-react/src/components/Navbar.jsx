// eslint-disable-next-line no-unused-vars
import React, { useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import api from "../api/client";
import { useSession } from "../context/SessionContext";
import BrandMark from "./BrandMark";
import ThemeToggle from "./ThemeToggle";
import Icon from "./ui/Icon";

const navItems = [
  { to: "/dashboard", label: "Inicio", icon: "home", section: "General" },
  { to: "/jobs", label: "Vacantes", icon: "briefcase", section: "Reclutamiento", permission: "jobs.read" },
  { to: "/applications", label: "Postulaciones", icon: "applications", section: "Reclutamiento", permission: "candidates.read" },
  { to: "/calendar", label: "Agenda", icon: "calendar", section: "Reclutamiento", permission: "candidates.read" },
  { to: "/candidates", label: "Candidatos", icon: "users", section: "Reclutamiento", permission: "candidates.read" },
  { to: "/ranking", label: "Ranking IA", icon: "ranking", section: "Reclutamiento", permission: "ranking.read" },
  { to: "/employees", label: "Empleados", icon: "employee", section: "Equipo", permission: "employees.read" },
  { to: "/access", label: "Usuarios y accesos", icon: "profile", section: "Equipo", permission: "employees.credentials.manage" },
  {
    to: "/attendance",
    label: "Asistencia",
    icon: "calendar",
    section: "Equipo",
    permissionsAny: [
      "talent_id.attendance.read_own",
      "talent_id.manage",
      "profile.read_own",
    ],
  },
  { to: "/direction/scores", label: "Calificación", icon: "star", section: "Equipo", permission: "employee_scores.read" },
  { to: "/training", label: "Capacitación", icon: "training", section: "Desarrollo", permission: "training.read" },
  {
    to: "/progress",
    label: "Mi progreso",
    icon: "progress",
    section: "Desarrollo",
    permission: "training.progress.read_own",
    roles: ["EMPLOYEE"],
  },
  {
    to: "/documents",
    label: "Documentos",
    icon: "applications",
    section: "Cuenta",
    permissionsAny: ["employee_documents.read_own", "employee_documents.read_all"],
  },
  { to: "/profile", label: "Mi perfil", icon: "profile", section: "Cuenta", permission: "profile.read_own" },
  { to: "/integrations", label: "Integraciones", icon: "integrations", section: "Sistema", permission: "integrations.manage" },
];

const sectionOrder = ["General", "Reclutamiento", "Equipo", "Desarrollo", "Cuenta", "Sistema"];

function primaryRole(roles = []) {
  if (roles.includes("ADMIN")) return "ADMIN";
  return "EMPLOYEE";
}

function Brand() {
  return (
    <NavLink to="/dashboard" className="navbar-brand" aria-label="ASIATI Talent Intelligence, inicio">
      <BrandMark />
    </NavLink>
  );
}

function roleLabel(roles = []) {
  const role = primaryRole(roles);
  if (role === "ADMIN") return "Administración";
  return "Empleado";
}

function Navbar() {
  const navigate = useNavigate();
  const { principal, hasPermission, clearSession } = useSession();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("asiati.sidebar.collapsed") === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  useEffect(() => {
    document.body.classList.toggle("nav-mobile-open", open);
    return () => document.body.classList.remove("nav-mobile-open");
  }, [open]);

  useEffect(() => {
    document.body.classList.toggle("nav-desktop-collapsed", collapsed);
    try {
      window.localStorage.setItem("asiati.sidebar.collapsed", String(collapsed));
    } catch {
      // Local storage can be unavailable in privacy-restricted browsers.
    }
    return () => document.body.classList.remove("nav-desktop-collapsed");
  }, [collapsed]);

  async function logout() {
    await api.post("/auth/logout").catch(() => {});
    clearSession();
    navigate("/login");
  }

  const role = primaryRole(principal?.roles);
  const visibleItems = navItems.filter(
    (item) => (
      (!item.permission || hasPermission(item.permission))
      && (
        !item.permissionsAny
        || item.permissionsAny.some((permission) => hasPermission(permission))
      )
      && (!item.roles || item.roles.includes(role))
    ),
  );

  const sections = useMemo(
    () => sectionOrder
      .map((section) => ({
        section,
        items: visibleItems.filter((item) => item.section === section),
      }))
      .filter((group) => group.items.length > 0),
    [visibleItems],
  );

  const profile = principal?.profile || {};
  const displayName = [profile.first_name, profile.last_name].filter(Boolean).join(" ")
    || principal?.email
    || "Usuario ASIATI";

  return (
    <>
      <header className="mobile-header">
        <Brand />
        <button
          className="menu-toggle"
          type="button"
          aria-expanded={open}
          aria-controls="primary-navigation"
          aria-label={open ? "Cerrar menú" : "Abrir menú"}
          onClick={() => setOpen((value) => !value)}
        >
          <span />
          <span />
        </button>
      </header>

      {open && (
        <button
          className="nav-backdrop"
          type="button"
          aria-label="Cerrar menú"
          onClick={() => setOpen(false)}
        />
      )}

      <aside className={`navbar ${open ? "is-open" : ""}`} aria-label="Navegación de la aplicación">
        <div className="navbar-inner">
          <div className="navbar-topline">
            <Brand />
            <button
              className={`desktop-menu-toggle ${collapsed ? "is-collapsed" : ""}`}
              type="button"
              aria-label={collapsed ? "Expandir menú lateral" : "Contraer menú lateral"}
              aria-pressed={collapsed}
              title={collapsed ? "Expandir menú" : "Contraer menú"}
              onClick={() => setCollapsed((value) => !value)}
            >
              <span />
              <span />
              <span />
            </button>
          </div>

          <div className="nav-context">
            <span className="nav-context-label">{roleLabel(principal?.roles)}</span>
            <strong title={displayName}>{displayName}</strong>
          </div>

          <nav id="primary-navigation" className="navbar-links" aria-label="Navegación principal">
            {sections.map(({ section, items }) => (
              <div className="nav-section" key={section}>
                <span className="nav-section-label">{section}</span>
                <div className="nav-section-items">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={() => setOpen(false)}
                      className={({ isActive }) => `navbar-link ${isActive ? "active" : ""}`}
                      title={collapsed ? item.label : undefined}
                      aria-label={collapsed ? item.label : undefined}
                    >
                      <span className="navbar-icon" aria-hidden="true">
                        <Icon name={item.icon} size={17} />
                      </span>
                      <span className="navbar-link-label">{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>

          <div className="nav-insight">
            <span className="nav-insight-dot" aria-hidden="true" />
            <div>
              <strong>{hasPermission("jobs.read") ? "Gestión de talento" : "Tu espacio ASIATI"}</strong>
              <span>{hasPermission("jobs.read") ? "Selección y desarrollo" : "Capacitación y progreso"}</span>
            </div>
          </div>

          <div className="navbar-bottom-actions">
            <ThemeToggle />
            <button
              className="navbar-logout"
              type="button"
              onClick={logout}
              title={collapsed ? "Cerrar sesión" : undefined}
              aria-label={collapsed ? "Cerrar sesión" : undefined}
            >
              <Icon name="logout" size={17} />
              <span>Cerrar sesión</span>
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

export default Navbar;
