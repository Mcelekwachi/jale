import { useEffect, useRef, useState } from "react";

export interface QuizChoice {
  label: string;
  isCorrect: boolean;
  isNeutral?: boolean;
}

interface QuizFeedbackProps {
  choices: QuizChoice[];
  onSelect: (choice: QuizChoice) => void;
  onContinue: () => void;
  disabled?: boolean;
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const update = () => setReduced(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  return reduced;
}

export function QuizFeedback({
  choices,
  onSelect,
  onContinue,
  disabled = false,
}: QuizFeedbackProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const advanced = useRef(false);
  const onContinueRef = useRef(onContinue);
  const reducedMotion = useReducedMotion();
  onContinueRef.current = onContinue;

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  function continueOnce() {
    if (advanced.current) return;
    advanced.current = true;
    if (timer.current) clearTimeout(timer.current);
    onContinueRef.current();
  }

  function choose(index: number) {
    if (selected !== null || disabled) return;
    setSelected(index);
    onSelect(choices[index]);
    timer.current = setTimeout(continueOnce, 800);
  }

  const selectedChoice = selected === null ? null : choices[selected];
  return (
    <div className="mt-8 space-y-3">
      {choices.map((choice, index) => {
        const isSelected = selected === index;
        const revealCorrect = selected !== null && choice.isCorrect;
        const isWrong = isSelected && !choice.isCorrect && !choice.isNeutral;
        const isNeutral = isSelected && choice.isNeutral;
        const state = isWrong
          ? "wrong"
          : isNeutral
            ? "neutral"
            : revealCorrect
              ? "correct"
              : "idle";
        const stateClass = {
          idle: "border-sand bg-white",
          correct: "border-[#2f6f45] bg-[#e2f1e5] text-[#174d2a]",
          wrong: "border-terracotta-dark bg-terracotta-soft text-terracotta-dark",
          neutral: "border-muted bg-[#eee9df] text-ink",
        }[state];
        const stateText = isWrong
          ? "Your answer · Incorrect"
          : isNeutral
            ? "Your answer · Not sure"
            : revealCorrect
              ? isSelected
                ? "Your answer · Correct"
                : "Correct answer"
              : null;
        const icon = isWrong ? "✕" : isNeutral ? "?" : revealCorrect ? "✓" : null;

        return (
          <button
            key={choice.label}
            type="button"
            disabled={disabled || selected !== null}
            onClick={() => choose(index)}
            className={`flex min-h-12 w-full items-center gap-3 rounded-xl border-2 px-4 text-left disabled:opacity-100 ${stateClass} ${reducedMotion ? "" : "transition-colors duration-200"}`}
          >
            {icon && (
              <span aria-hidden="true" className="font-bold">
                {icon}
              </span>
            )}
            <span>{choice.label}</span>
            {stateText && (
              <span className="ml-auto text-sm font-bold">{stateText}</span>
            )}
          </button>
        );
      })}
      {selectedChoice && (
        <>
          <p role="status" className="font-bold">
            {selectedChoice.isNeutral
              ? "Not sure — here is the answer"
              : selectedChoice.isCorrect
                ? "✓ Correct"
                : "✕ Not quite"}
          </p>
          <button
            type="button"
            disabled={disabled}
            onClick={continueOnce}
            className="min-h-12 w-full rounded-xl bg-indigo-deep font-bold text-cream"
          >
            Continue
          </button>
        </>
      )}
    </div>
  );
}
