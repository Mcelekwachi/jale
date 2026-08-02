import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { Spinner } from "../components/Spinner";
import { supabase } from "../lib/supabase";

export function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    void (async () => {
      try {
        const code = new URLSearchParams(window.location.search).get("code");
        const result = code
          ? await supabase.auth.exchangeCodeForSession(code)
          : await supabase.auth.getSession();
        if (result.error) throw result.error;
        navigate("/", { replace: true });
      } catch (error) {
        navigate("/signin", {
          replace: true,
          state: {
            message:
              error instanceof Error
                ? error.message
                : "We could not complete sign-in",
          },
        });
      }
    })();
  }, [navigate]);

  return <Spinner label="Completing sign-in" fullScreen />;
}
