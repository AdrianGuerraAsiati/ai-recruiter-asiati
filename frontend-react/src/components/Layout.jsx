import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import Navbar from "./Navbar";
import Footer from "./Footer";

const pageTitles = {
  "/dashboard": "Inicio",
  "/jobs": "Vacantes",
  "/applications": "Postulaciones",
  "/candidates": "Candidatos",
  "/ranking": "Ranking IA",
  "/employees": "Empleados",
  "/access": "Usuarios y accesos",
  "/talent-id": "Talent ID",
  "/attendance": "Asistencia",
  "/direction/scores": "Calificación de empleados",
  "/training": "Capacitación",
  "/progress": "Mi progreso",
  "/profile": "Mi perfil",
  "/integrations": "Integraciones",
  "/forbidden": "Acceso restringido",
};


function Layout({ children }) {
  const location = useLocation();

  useEffect(() => {
    const route = Object.keys(pageTitles).find((path) => (
      location.pathname === path || (path === "/candidates" && location.pathname.startsWith("/candidates/"))
    ));
    document.title = `${pageTitles[route] || "Talent Intelligence"} · ASIATI`;
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  return (
    <div className="app-layout">
      <a className="skip-link" href="#main-content">Saltar al contenido</a>
      <Navbar />
      <div className="app-content">
        <main id="main-content" className="app-main">{children}</main>
        <Footer />
      </div>
    </div>
  );
}

export default Layout;
