import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireActiveSubscription, RequireAuth, RequireBusiness, RequireNoBusiness } from "./components/RouteGuards";
import Landing from "./pages/Landing";
import LawyersLanding from "./pages/LawyersLanding";
import Signup from "./pages/Signup";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Dashboard from "./pages/Dashboard";
import Conversation from "./pages/Conversation";
import Settings from "./pages/Settings";
import Billing from "./pages/Billing";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/lawyers" element={<LawyersLanding />} />
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
                  <RequireActiveSubscription>
                    <Dashboard />
                  </RequireActiveSubscription>
                </RequireBusiness>
              </RequireAuth>
            }
          />
          <Route
            path="/app/conversations"
            element={
              <RequireAuth>
                <RequireBusiness>
                  <RequireActiveSubscription>
                    <Conversation />
                  </RequireActiveSubscription>
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
          <Route
            path="/app/billing"
            element={
              <RequireAuth>
                <RequireBusiness>
                  <Billing />
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
