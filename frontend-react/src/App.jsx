// eslint-disable-next-line no-unused-vars
import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Login from "./auth/Login";
import Layout from "./components/Layout";
import { ThemeProvider } from "./context/ThemeContext";
import { SessionProvider, useSession } from "./context/SessionContext";
import { NoticeProvider } from "./context/NoticeContext";

import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import Candidates from "./pages/Candidates";
import RecruitmentCalendar from "./pages/RecruitmentCalendar";
import Ranking from "./pages/Ranking";
import CandidateDetail from "./pages/CandidateDetail";
import Integrations from "./pages/Integrations";
import Employees from "./pages/Employees";
import AccessManagement from "./pages/AccessManagement";
import AttendanceSettings from "./pages/TalentId";
import Attendance from "./pages/Attendance";
import Training from "./pages/Training";
import EmployeeScores from "./pages/EmployeeScores";
import Applications from "./pages/Applications";
import Progress from "./pages/Progress";
import Profile from "./pages/Profile";
import Forbidden from "./pages/Forbidden";
import NotFound from "./pages/NotFound";
import "./ui-system.css";


function ProtectedRoute({ children, permission, permissionsAny = [] }) {
  const { status, hasPermission } = useSession();

  if (status === "loading") {
    return <div className="session-loading"><span aria-hidden="true" />Validando acceso seguro…</div>;
  }

  if (status !== "authenticated") {
    return <Navigate to="/login" replace />;
  }

  const hasRequiredPermission = (
    (!permission || hasPermission(permission))
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


function ProtectedPage({ children, permission, permissionsAny }) {
  return (
    <ProtectedRoute permission={permission} permissionsAny={permissionsAny}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}


function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route path="/dashboard" element={<ProtectedPage><Dashboard /></ProtectedPage>} />
      <Route path="/training" element={<ProtectedPage permission="training.read"><Training /></ProtectedPage>} />
      <Route path="/progress" element={<ProtectedPage permission="training.progress.read_own"><Progress /></ProtectedPage>} />
      <Route path="/profile" element={<ProtectedPage permission="profile.read_own"><Profile /></ProtectedPage>} />
      <Route path="/employees" element={<ProtectedPage permission="employees.read"><Employees /></ProtectedPage>} />
      <Route path="/access" element={<ProtectedPage permission="employees.credentials.manage"><AccessManagement /></ProtectedPage>} />
      <Route path="/talent-id" element={<Navigate to="/attendance" replace />} />
      <Route path="/attendance/settings" element={<ProtectedPage permission="talent_id.manage"><AttendanceSettings /></ProtectedPage>} />
      <Route
        path="/attendance"
        element={(
          <ProtectedPage
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
      <Route path="/ranking" element={<ProtectedPage permission="ranking.read"><Ranking /></ProtectedPage>} />
      <Route path="/integrations" element={<ProtectedPage permission="integrations.manage"><Integrations /></ProtectedPage>} />
      <Route
        path="/candidates/:candidate_id"
        element={<ProtectedPage permission="candidates.read"><CandidateDetail /></ProtectedPage>}
      />
      <Route path="/forbidden" element={<ProtectedPage><Forbidden /></ProtectedPage>} />

      <Route path="/register" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<ProtectedPage><NotFound /></ProtectedPage>} />
    </Routes>
  );
}


function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <SessionProvider>
          <NoticeProvider>
            <AppRoutes />
          </NoticeProvider>
        </SessionProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
