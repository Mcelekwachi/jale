import type { Choice } from "./options";

interface OptionListProps<T extends string | number> {
  choices: readonly Choice<T>[];
  selected?: T | null;
  onSelect: (value: T) => void;
  disabled?: boolean;
}

export function OptionList<T extends string | number>({
  choices,
  selected,
  onSelect,
  disabled,
}: OptionListProps<T>) {
  return (
    <div className="grid gap-3">
      {choices.map((choice) => {
        const active = selected === choice.value;
        return (
          <button
            key={choice.value}
            type="button"
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onSelect(choice.value)}
            className={`min-h-11 rounded-2xl border-2 px-4 py-3 text-left font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ochre disabled:opacity-60 ${
              active
                ? "border-indigo-deep bg-indigo-deep text-cream shadow-card"
                : "border-sand bg-white text-indigo-deep hover:border-ochre hover:bg-ochre-soft"
            }`}
          >
            {choice.label}
          </button>
        );
      })}
    </div>
  );
}
