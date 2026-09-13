import type { ButtonHTMLAttributes, PropsWithChildren } from "react";
import { useUiStrings } from "../i18n/useUiStrings";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  busy?: boolean;
}

export function Button({
  children,
  className = "",
  variant = "primary",
  busy,
  disabled,
  ...props
}: PropsWithChildren<ButtonProps>) {
  const strings = useUiStrings().shared;
  const colors =
    variant === "primary"
      ? "bg-indigo-deep text-cream hover:bg-indigo-rich"
      : "border border-ochre text-indigo-deep hover:bg-ochre-soft";
  return (
    <button
      className={`min-h-11 w-full rounded-2xl px-5 py-3 font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ochre disabled:cursor-not-allowed disabled:opacity-60 ${colors} ${className}`}
      disabled={disabled || busy}
      {...props}
    >
      {busy ? strings.pleaseWait : children}
    </button>
  );
}
