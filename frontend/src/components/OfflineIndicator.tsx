import { useEffect, useState } from "react";

export function OfflineIndicator() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  if (online) return null;
  return (
    <div role="status" aria-label="Offline" className="fixed left-1/2 top-3 z-50 -translate-x-1/2 rounded-full bg-indigo-deep px-4 py-2 text-sm font-semibold text-cream shadow-card">
      You’re offline
    </div>
  );
}
