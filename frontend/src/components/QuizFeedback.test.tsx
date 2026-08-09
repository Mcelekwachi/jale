import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuizFeedback } from "./QuizFeedback";

const choices = [
  { label: "Right", isCorrect: true },
  { label: "Wrong", isCorrect: false },
];

describe("QuizFeedback", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("automatically advances after 800ms", () => {
    const onContinue = vi.fn();
    render(
      <QuizFeedback
        choices={choices}
        onSelect={vi.fn()}
        onContinue={onContinue}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Right" }));
    act(() => vi.advanceTimersByTime(799));
    expect(onContinue).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(onContinue).toHaveBeenCalledOnce();
  });

  it("advances only once when Continue wins the timer race", () => {
    const onContinue = vi.fn();
    render(
      <QuizFeedback
        choices={choices}
        onSelect={vi.fn()}
        onContinue={onContinue}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Wrong" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    act(() => vi.advanceTimersByTime(800));

    expect(onContinue).toHaveBeenCalledOnce();
  });

  it("cancels automatic advancement when the question unmounts", () => {
    const onContinue = vi.fn();
    const view = render(
      <QuizFeedback
        choices={choices}
        onSelect={vi.fn()}
        onContinue={onContinue}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Right" }));
    view.unmount();
    act(() => vi.advanceTimersByTime(800));

    expect(onContinue).not.toHaveBeenCalled();
  });
});
