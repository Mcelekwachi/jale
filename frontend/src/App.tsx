import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { OnboardingGuard } from "./auth/OnboardingGuard";
import { AuthCallback } from "./routes/AuthCallback";
import { Home } from "./routes/Home";
import { Onboarding } from "./routes/Onboarding";
import { AdminErrorBoundary, AdminRoute } from "./routes/Admin";
import {
  AdminContentDetailRoute,
  AdminContentList,
} from "./routes/AdminContent";
import { NotFound } from "./routes/NotFound";
import { Settings } from "./routes/Settings";
import { SignIn } from "./routes/SignIn";
import { Study } from "./routes/Study";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route element={<ProtectedRoute />}>
            <Route
              path="/admin"
              element={
                <AdminErrorBoundary>
                  <AdminRoute />
                </AdminErrorBoundary>
              }
            />
            <Route
              path="/admin/content"
              element={
                <AdminErrorBoundary>
                  <AdminRoute>
                    <AdminContentList />
                  </AdminRoute>
                </AdminErrorBoundary>
              }
            />
            <Route
              path="/admin/content/:contentId"
              element={
                <AdminErrorBoundary>
                  <AdminRoute>
                    <AdminContentDetailRoute />
                  </AdminRoute>
                </AdminErrorBoundary>
              }
            />
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/onboarding/:step" element={<Onboarding />} />
            <Route element={<OnboardingGuard />}>
              <Route path="/" element={<Home />} />
              <Route path="/settings" element={<Settings />} />
              <Route
                path="/study/:trackSlug/:unitPosition"
                element={<Study />}
              />
            </Route>
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
