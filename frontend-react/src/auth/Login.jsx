import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { setAccessToken } from "../api/client";
import BrandMark from "../components/BrandMark";
import { getApiErrorMessage } from "../utils/errors";
import { useSession } from "../context/SessionContext";

function AuthBrand() {
  return (
    <div className="auth-brand">
      <BrandMark />
    </div>
  );
}

function Login() {
  const navigate = useNavigate();
  const { refreshSession } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const { data } = await api.post("/auth/login", { email, password });
      setAccessToken(data.access_token);
      await refreshSession();
      navigate("/dashboard");
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "iniciar sesión",
        resource: "tu cuenta",
        fallback: "El correo o la contraseña no coinciden con una cuenta activa. Verifica ambos datos antes de reintentar.",
        statusMessages: {
          401: "El correo o la contraseña no coinciden con una cuenta activa. Verifica ambos datos antes de reintentar.",
        },
      }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-story auth-talent-story" aria-label="Presentación de ASIATI Talent Intelligence">
        <AuthBrand />
        <div className="auth-story-content auth-talent-story-content">
          <span className="eyebrow eyebrow-dark"><i /> Plataforma de talento ASIATI</span>
          <h1>Del primer contacto al <em>crecimiento de cada persona.</em></h1>
          <p>
            Talent Intelligence conecta selección, gestión de equipo y desarrollo
            en una sola experiencia para tomar mejores decisiones sobre las personas.
          </p>

          <div className="auth-capability-grid" aria-label="Capacidades de Talent Intelligence">
            <article>
              <span>01</span>
              <div>
                <strong>Reclutamiento inteligente</strong>
                <small>Vacantes, postulaciones, candidatos, ranking IA y agenda.</small>
              </div>
            </article>
            <article>
              <span>02</span>
              <div>
                <strong>Gestión de personas</strong>
                <small>Empleados, seguimiento y evaluación desde un mismo lugar.</small>
              </div>
            </article>
            <article>
              <span>03</span>
              <div>
                <strong>Desarrollo y onboarding</strong>
                <small>Capacitación, progreso y acompañamiento desde el primer día.</small>
              </div>
            </article>
          </div>
        </div>

        <div className="auth-product-summary" aria-hidden="true">
          <div className="auth-product-summary-orbit">
            <span>Talent</span>
            <strong>360°</strong>
          </div>
          <span>Selección</span>
          <span>Equipo</span>
          <span>Desarrollo</span>
        </div>

        <p className="auth-story-footer">ASIATI · Talent Intelligence · Selección · Equipo · Desarrollo</p>
      </section>

      <section className="auth-panel">
        <div className="auth-mobile-brand"><AuthBrand /></div>
        <div className="auth-card">
          <div className="auth-heading auth-login-heading">
            <span className="eyebrow">Talent Intelligence</span>
            <h2>Bienvenido</h2>
            <p>Accede a tu espacio de reclutamiento, equipo o aprendizaje según tu rol.</p>
            <div className="auth-role-strip" aria-label="Áreas de la plataforma">
              <span>Reclutamiento</span>
              <span>Personas</span>
              <span>Capacitación</span>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="email">Correo electrónico</label>
              <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nombre@empresa.com" autoComplete="email" required />
            </div>
            <div className="form-group">
              <label htmlFor="password">Contraseña</label>
              <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Ingresa tu contraseña" autoComplete="current-password" required />
            </div>

            {error && <div className="login-error" role="alert">{error}</div>}

            <button type="submit" className="login-button" disabled={loading}>
              {loading ? "Verificando acceso…" : "Iniciar sesión"}
              {!loading && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <p className="login-register">El acceso es administrado por el equipo autorizado de ASIATI.</p>
          <p className="auth-security"><span aria-hidden="true">●</span> Acceso corporativo protegido</p>
        </div>
      </section>
    </main>
  );
}

export default Login;
