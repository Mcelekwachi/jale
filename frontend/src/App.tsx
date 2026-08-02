import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { OnboardingGuard } from "./auth/OnboardingGuard";
import { AuthCallback } from "./routes/AuthCallback";
import { Home } from "./routes/Home";
import { Onboarding } from "./routes/Onboarding";
import { Settings } from "./routes/Settings";
import { SignIn } from "./routes/SignIn";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/onboarding/:step" element={<Onboarding />} />
            <Route element={<OnboardingGuard />}>
              <Route path="/" element={<Home />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
