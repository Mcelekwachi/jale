interface ErrorMessageProps {
  message: string;
}

export function ErrorMessage({ message }: ErrorMessageProps) {
  return (
    <p
      role="alert"
      className="rounded-xl border border-terracotta/30 bg-terracotta-soft px-4 py-3 text-sm text-terracotta-dark"
    >
      {message}
    </p>
  );
}
