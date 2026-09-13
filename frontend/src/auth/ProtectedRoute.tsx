import { Navigate, Outlet, useLocation } from "react-router-dom";

import { Spinner } from "../components/Spinner";
import { useUiStrings } from "../i18n/useUiStrings";
import { useAuth } from "./useAuth";

export function ProtectedRoute() {
  const { loading, user } = useAuth();
  const location = useLocation();
  const strings = useUiStrings().shared;

  if (loading) return <Spinner label={strings.checkingSession} fullScreen />;
  if (!user) {
    return (
      <Navigate
        to="/signin"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }
  return <Outlet />;
}
