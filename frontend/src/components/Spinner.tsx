interface SpinnerProps {
  label?: string;
  fullScreen?: boolean;
}

export function Spinner({
  label = "Loading",
  fullScreen = false,
}: SpinnerProps) {
  return (
    <div
      className={
        fullScreen
          ? "grid min-h-dvh place-content-center bg-warm"
          : "grid place-items-center gap-3 py-8"
      }
    >
      <div
        role="status"
        aria-label={label}
        className="grid justify-items-center gap-3 text-indigo-deep"
      >
        <span className="size-9 animate-spin rounded-full border-4 border-ochre-soft border-t-indigo-deep motion-reduce:animate-none" />
        <span className="text-sm font-semibold">{label}</span>
      </div>
    </div>
  );
}
