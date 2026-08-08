import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../lib/api";
import type { StudyItem } from "../lib/types";
import { Study } from "./Study";

vi.mock("../lib/api");
const baseItem: StudyItem = {
  id: 7,
  content_type: "word",
  prompt: "Ndewo",
  answer: "Hello",
  meta_language: "eng",
  meta_language_used: "eng",
  audio_url: null,
  audio_state: "missing",
  verified: true,
  flag_count: 0,
};

function setup(mode: string, item: StudyItem = baseItem) {
  vi.mocked(apiFetch).mockImplementation(async (path = "/v1/me") => {
    if (path === "/v1/me")
      return { preferences: { meta_language: "eng" } } as never;
    if (path === "/v1/languages/meta")
      return [{ code: "eng", name: "English" }] as never;
    if (String(path).includes("/items"))
      return {
        track: "foundations",
        unit_position: 1,
        unit_title: "Greetings",
        mode,
        items: [item],
      } as never;
    if (path === "/v1/study/answers")
      return {
        results: [{ client_answer_id: "x", status: "accepted" }],
        current_streak: 2,
        today_xp: 10,
      } as never;
    if (String(path).includes("/flag")) return { id: 1 } as never;
    throw new Error(`Unexpected ${path}`);
  });
  render(
    <MemoryRouter initialEntries={["/study/foundations/1"]}>
      <Routes>
        <Route path="/study/:trackSlug/:unitPosition" element={<Study />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Study", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());
  it("renders flashcards with reveal and rating controls", async () => {
    setup("flashcard");
    expect(await screen.findByText("Ndewo")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /reveal/i }));
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /i knew it/i }),
    ).toBeInTheDocument();
  });
  it("renders phrase practice details", async () => {
    setup("phrase_practice", {
      ...baseItem,
      literal_translation: "literal",
      example_sentence: "Ọ dị mma",
      example_translation: "It is good",
    });
    await screen.findByText("Ndewo");
    await userEvent.click(screen.getByRole("button", { name: /reveal/i }));
    expect(screen.getByText("literal")).toBeInTheDocument();
    expect(screen.getByText("Ọ dị mma")).toBeInTheDocument();
  });
  it("renders the full proverb cultural note", async () => {
    const note =
      "A long cultural note that must remain entirely visible and never be truncated.";
    setup("proverbs", {
      ...baseItem,
      content_type: "proverb",
      cultural_note: note,
    });
    await screen.findByText("Ndewo");
    await userEvent.click(screen.getByRole("button", { name: /reveal/i }));
    expect(screen.getByText(note)).toBeInTheDocument();
  });
  it("locks a quiz after marking the correct option", async () => {
    setup("quiz", {
      ...baseItem,
      prompt: "Hello",
      answer: "Ndewo",
      options: [
        { text: "Ndewo", is_correct: true },
        { text: "Daalụ", is_correct: false },
      ],
    });
    await screen.findByText("Hello");
    await userEvent.click(screen.getByRole("button", { name: "Ndewo" }));
    expect(screen.getByText(/correct/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Daalụ" })).toBeDisabled();
  });
  it("shows missing audio as a disabled control", async () => {
    setup("flashcard");
    expect(
      await screen.findByRole("button", { name: /audio coming soon/i }),
    ).toBeDisabled();
  });
  it("scopes translation flags to the meta language but not audio flags", async () => {
    setup("flashcard");
    await screen.findByText("Ndewo");
    await userEvent.click(screen.getByRole("button", { name: /flag/i }));
    await userEvent.click(screen.getByLabelText(/translation is wrong/i));
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/content/7/flag",
      expect.objectContaining({
        body: expect.stringContaining('"meta_language":"eng"'),
      }),
    );
  });
  it("omits meta language for item-level flags and acknowledges repeats", async () => {
    setup("flashcard");
    await screen.findByText("Ndewo");
    await userEvent.click(screen.getByRole("button", { name: /flag/i }));
    await userEvent.click(screen.getByLabelText(/audio is wrong/i));
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));
    const first = vi
      .mocked(apiFetch)
      .mock.calls.find(([path]) => String(path).includes("/flag"));
    expect(first?.[1]?.body).not.toContain("meta_language");
    await userEvent.click(screen.getByRole("button", { name: /flag/i }));
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));
    expect(
      await screen.findByText(/thanks, already reported/i),
    ).toBeInTheDocument();
  });
});
