// eslint-disable-next-line no-unused-vars
import React, { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import Login from "./auth/Login";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./context/ThemeContext";
import { SessionProvider, useSession } from "./context/SessionContext";
import { NoticeProvider } from "./context/NoticeContext";

// Carga diferida por ruta: la página pública de la prueba psicotécnica y las
// pantallas de administración no deben descargarse en el primer render.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Jobs = lazy(() => import("./pages/Jobs"));
const Candidates = lazy(() => import("./pages/Candidates"));
const RecruitmentCalendar = lazy(() => import("./pages/RecruitmentCalendar"));
const Ranking = lazy(() => import("./pages/Ranking"));
const CandidateDetail = lazy(() => import("./pages/CandidateDetail"));
const Integrations = lazy(() => import("./pages/Integrations"));
const Employees = lazy(() => import("./pages/Employees"));
const AccessManagement = lazy(() => import("./pages/AccessManagement"));
const AttendanceSettings = lazy(() => import("./pages/TalentId"));
const Attendance = lazy(() => import("./pages/Attendance"));
const Training = lazy(() => import("./pages/Training"));
const EmployeeScores = lazy(() => import("./pages/EmployeeScores"));
const Applications = lazy(() => import("./pages/Applications"));
const Progress = lazy(() => import("./pages/Progress"));
const Profile = lazy(() => import("./pages/Profile"));
const Documents = lazy(() => import("./pages/Documents"));
const Psychotechnical = lazy(() => import("./pages/Psychotechnical"));
const PsychotechnicalTake = lazy(() => import("./pages/PsychotechnicalTake"));
const MyPsychotechnical = lazy(() => import("./pages/MyPsychotechnical"));
const Forbidden = lazy(() => import("./pages/Forbidden"));
const NotFound = lazy(() => import("./pages/NotFound"));
import "./ui-system.css";


function ProtectedRoute({ children, permission, permissionsAny = [], rolesAny = [] }) {
  const { status, hasPermission, principal } = useSession();
  const location = useLocation();

  if (status === "loading") {
    return <div className="session-loading"><span aria-hidden="true" />Validando acceso seguro…</div>;
  }

  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const hasRequiredPermission = (
    (rolesAny.length === 0 || rolesAny.some((role) => principal?.roles?.includes(role)))
    && (!permission || hasPermission(permission))
    && (
      permissionsAny.length === 0
      || permissionsAny.some((candidate) => hasPermission(candidate))
    )
  );

  if (!hasRequiredPermission) {
    return <Navigate to="/forbidden" replace />;
  }

  return children;
}


function ProtectedPage({ children, permission, permissionsAny, rolesAny }) {
  return (
    <ProtectedRoute permission={permission} permissionsAny={permissionsAny} rolesAny={rolesAny}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}


function LandingPage() {
  const { principal } = useSession();
  if (principal?.roles?.includes("APPLICANT") && !principal?.roles?.includes("EMPLOYEE") && !principal?.roles?.includes("ADMIN")) {
    return <Navigate to="/documents" replace />;
  }
  return <Dashboard />;
}

function PageLoading() {
  return (
    <div className="session-loading" role="status" aria-live="polite">
      <span aria-hidden="true" />
      Cargando…
    </div>
  );
}


function AppRoutes() {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
      <Route path="/login" element={<Login />} />

      <Route path="/dashboard" element={<ProtectedPage><LandingPage /></ProtectedPage>} />
      <Route path="/training" element={<ProtectedPage permission="training.read"><Training /></ProtectedPage>} />
      <Route path="/progress" element={<ProtectedPage permission="training.progress.read_own"><Progress /></ProtectedPage>} />
      <Route path="/profile" element={<ProtectedPage permission="profile.read_own"><Profile /></ProtectedPage>} />
      <Route
        path="/documents"
        element={(
          <ProtectedPage permissionsAny={["employee_documents.read_own", "employee_documents.read_all"]}>
            <Documents />
          </ProtectedPage>
        )}
      />
      <Route path="/employees" element={<ProtectedPage permission="employees.read"><Employees /></ProtectedPage>} />
      <Route path="/access" element={<ProtectedPage permission="employees.credentials.manage"><AccessManagement /></ProtectedPage>} />
      <Route path="/talent-id" element={<Navigate to="/attendance" replace />} />
      <Route path="/attendance/settings" element={<ProtectedPage permission="talent_id.manage"><AttendanceSettings /></ProtectedPage>} />
      <Route
        path="/attendance"
        element={(
          <ProtectedPage
            rolesAny={["ADMIN", "EMPLOYEE"]}
            permissionsAny={[
              "talent_id.attendance.read_own",
              "talent_id.manage",
              "profile.read_own",
            ]}
          >
            <Attendance />
          </ProtectedPage>
        )}
      />
      <Route path="/direction/scores" element={<ProtectedPage permission="employee_scores.read"><EmployeeScores /></ProtectedPage>} />
      <Route path="/jobs" element={<ProtectedPage permission="jobs.read"><Jobs /></ProtectedPage>} />
      <Route path="/applications" element={<ProtectedPage permission="candidates.read"><Applications /></ProtectedPage>} />
      <Route path="/calendar" element={<ProtectedPage permission="candidates.read"><RecruitmentCalendar /></ProtectedPage>} />
      <Route path="/candidates" element={<ProtectedPage permission="candidates.read"><Candidates /></ProtectedPage>} />
      <Route path="/psychotechnical/take/:token" element={<PsychotechnicalTake />} />
      <Route path="/my-psychotechnical" element={<ProtectedPage><MyPsychotechnical /></ProtectedPage>} />
      <Route path="/ranking" element={<ProtectedPage permission="ranking.read"><Ranking /></ProtectedPage>} />
      <Route path="/psychotechnical" element={<ProtectedPage permission="psychotechnical.read"><Psychotechnical /></ProtectedPage>} />
      <Route path="/integrations" element={<ProtectedPage permission="integrations.manage"><Integrations /></ProtectedPage>} />
      <Route
        path="/candidates/:candidate_id"
        element={<ProtectedPage permission="candidates.read"><CandidateDetail /></ProtectedPage>}
      />
      <Route path="/forbidden" element={<ProtectedPage><Forbidden /></ProtectedPage>} />

      <Route path="/register" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<ProtectedPage><NotFound /></ProtectedPage>} />
      </Routes>
    </Suspense>
  );
}


function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <SessionProvider>
          <NoticeProvider>
            <ErrorBoundary
              title="La aplicación encontró un error inesperado"
              className="ui-error-boundary--global"
            >
              <AppRoutes />
            </ErrorBoundary>
          </NoticeProvider>
        </SessionProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
