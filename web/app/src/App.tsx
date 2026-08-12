import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequireBusiness, RequireNoBusiness } from "./components/RouteGuards";
import Landing from "./pages/Landing";
import Signup from "./pages/Signup";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Dashboard from "./pages/Dashboard";
import Conversation from "./pages/Conversation";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/login" element={<Login />} />
          <Route
            path="/onboarding"
            element={
              <RequireAuth>
                <RequireNoBusiness>
                  <Onboarding />
                </RequireNoBusiness>
              </RequireAuth>
            }
          />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <RequireBusiness>
                  <Dashboard />
                </RequireBusiness>
              </RequireAuth>
            }
          />
          <Route
            path="/app/conversations"
            element={
              <RequireAuth>
                <RequireBusiness>
                  <Conversation />
                </RequireBusiness>
              </RequireAuth>
            }
          />
          <Route
            path="/app/settings"
            element={
              <RequireAuth>
                <RequireBusiness>
                  <Settings />
                </RequireBusiness>
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
