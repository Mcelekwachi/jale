import { useEffect, useState } from "react";
import { registerSW } from "virtual:pwa-register";

export function UpdatePrompt() {
  const [update, setUpdate] = useState<((reloadPage?: boolean) => Promise<void>) | null>(null);
  useEffect(() => {
    const applyUpdate = registerSW({
      immediate: true,
      onNeedRefresh() {
        setUpdate(() => applyUpdate);
      },
    });
  }, []);
  if (!update) return null;
  return (
    <div role="status" className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md items-center justify-between gap-4 rounded-2xl bg-indigo-deep p-4 text-cream shadow-card">
      <span>Update available</span>
      <button type="button" className="min-h-11 rounded-xl bg-cream px-4 font-bold text-indigo-deep" onClick={() => void update(true)}>
        Reload
      </button>
    </div>
  );
}
