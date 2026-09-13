import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { answerQueue } from "../study/answerQueueService";
import { Home } from "./Home";
import { setUiLanguage } from "../i18n/useUiStrings";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ signOut: vi.fn() }) }));
vi.mock("../lib/api");

const track = {
  track: {
    slug: "ibo_foundations",
    name: "Foundations",
    min_difficulty: "beginner",
    max_difficulty: "intermediate",
    is_default: true,
    units: [
      {
        position: 1,
        title: "Greetings",
        mode: "flashcard",
        item_count: 10,
        available: 10,
        progress: { done: 0, total: 10 },
        completed: false,
      },
      {
        position: 2,
        title: "Proverbs",
        mode: "proverbs",
        item_count: 4,
        available: 0,
        progress: { done: 0, total: 4 },
        completed: false,
      },
    ],
  },
  is_fallback: true,
};

describe("Home", () => {
  beforeEach(() => {
    setUiLanguage("eng");
    vi.mocked(apiFetch).mockReset();
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: undefined,
    });
  });

  it("renders Dutch interface text for the Dutch meta-language", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 1,
        today_goal_met: false,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "nld" } } as never)
      .mockResolvedValueOnce([{ code: "nld", name: "Dutch" }] as never);
    render(<Home />, { wrapper: MemoryRouter });
    expect(
      await screen.findByRole("link", { name: /instellingen/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Je leerpad")).toBeInTheDocument();
  });

  it("shows track, due review, progress, and keeps every unit accessible", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 3,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [{ id: 99 }] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "eng" } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "Dutch" }] as never);

    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/study/:track/:unit"
            element={<p>Study destination</p>}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("link", { name: /settings/i }),
    ).toHaveAttribute("href", "/settings");
    expect(screen.getByText("Foundations")).toBeInTheDocument();
    expect(screen.getByText(/learning with Dutch/i)).toBeInTheDocument();
    expect(screen.getByText(/3 day streak/i)).toBeInTheDocument();
    expect(screen.getByText(/today's goal met/i)).toBeInTheDocument();
    expect(screen.getByText(/review due/i)).toHaveTextContent("1");
    expect(
      screen.getByRole("link", { name: /start greetings/i }),
    ).toHaveAttribute("href", "/study/ibo_foundations/1");
    expect(screen.getByRole("link", { name: /proverbs/i })).toHaveAttribute(
      "href",
      "/study/ibo_foundations/2",
    );
  });

  it("invites a new learner instead of rendering a zero streak badge", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 0,
        today_goal_met: false,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: null } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);
    render(<Home />, { wrapper: MemoryRouter });
    expect(
      await screen.findByText(/start your streak today/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/0 day streak/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/review due/i)).not.toBeInTheDocument();
  });

  it("continues with the first incomplete unit instead of always unit one", async () => {
    const progressedTrack = {
      ...track,
      track: {
        ...track.track,
        units: [
          {
            ...track.track.units[0],
            progress: { done: 10, total: 10 },
            completed: true,
          },
          {
            ...track.track.units[1],
            title: "Wisdom",
            available: 4,
          },
        ],
      },
    };
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(progressedTrack as never)
      .mockResolvedValueOnce({
        current_streak: 2,
        today_goal_met: false,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "eng" } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);

    render(<Home />, { wrapper: MemoryRouter });

    const continueCard = await screen.findByRole("region", {
      name: /continue/i,
    });
    expect(continueCard).toHaveTextContent("Wisdom");
    expect(continueCard).toHaveTextContent("Proverbs");
    expect(continueCard).toHaveTextContent("Start");
    expect(screen.getByRole("link", { name: /start wisdom/i })).toHaveAttribute(
      "href",
      "/study/ibo_foundations/2",
    );
  });

  it("keeps every unit available in a compact secondary path list", async () => {
    const availableTrack = {
      ...track,
      track: {
        ...track.track,
        units: track.track.units.map((unit) => ({
          ...unit,
          available: unit.item_count,
        })),
      },
    };
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(availableTrack as never)
      .mockResolvedValueOnce({
        current_streak: 1,
        today_goal_met: false,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "eng" } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);

    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/study/:track/:unit"
            element={<p>Study destination</p>}
          />
        </Routes>
      </MemoryRouter>,
    );

    const path = await screen.findByRole("region", {
      name: /full learning path/i,
    });
    expect(path).toHaveClass("text-sm");
    expect(path).toHaveTextContent("Greetings");
    expect(path).toHaveTextContent("Proverbs");
    const secondUnit = screen.getByRole("link", { name: /2.*proverbs/i });
    expect(secondUnit).toHaveAttribute("href", "/study/ibo_foundations/2");
    await userEvent.click(secondUnit);
    expect(screen.getByText("Study destination")).toBeInTheDocument();
  });

  it("points to review due when every unit is complete", async () => {
    const completedTrack = {
      ...track,
      track: {
        ...track.track,
        units: track.track.units.map((unit) => ({
          ...unit,
          progress: { done: unit.item_count, total: unit.item_count },
          completed: true,
        })),
      },
    };
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(completedTrack as never)
      .mockResolvedValueOnce({
        current_streak: 4,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [{ id: 99 }] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "eng" } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);

    render(<Home />, { wrapper: MemoryRouter });

    const continueCard = await screen.findByRole("region", {
      name: /continue/i,
    });
    expect(continueCard).toHaveTextContent(/path complete/i);
    expect(screen.getByRole("link", { name: /review due/i })).toHaveAttribute(
      "href",
      "#review-due",
    );
  });

  it("does not render a dead review link when the path is complete with nothing due", async () => {
    const completedTrack = {
      ...track,
      track: {
        ...track.track,
        units: track.track.units.map((unit) => ({
          ...unit,
          progress: { done: unit.item_count, total: unit.item_count },
          completed: true,
        })),
      },
    };
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(completedTrack as never)
      .mockResolvedValueOnce({
        current_streak: 4,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "eng" } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);

    render(<Home />, { wrapper: MemoryRouter });

    const continueCard = await screen.findByRole("region", {
      name: /continue/i,
    });
    expect(continueCard).toHaveTextContent(/path complete/i);
    expect(continueCard).toHaveTextContent(/nothing to review right now/i);
    expect(
      screen.queryByRole("link", { name: /review due/i }),
    ).not.toBeInTheDocument();
  });

  it("shows queued answers and lets the learner sync them", async () => {
    await answerQueue.add({
      content_id: 7,
      correct: true,
      mode: "flashcard",
      duration_ms: 42,
    });
    const [pending] = await answerQueue.list();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 1,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "eng" } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never)
      .mockResolvedValueOnce({
        results: [
          {
            content_id: 7,
            client_answer_id: pending.client_answer_id,
            status: "accepted",
          },
        ],
        current_streak: 1,
        today_xp: 1,
      } as never);

    render(<Home />, { wrapper: MemoryRouter });

    expect(await screen.findByText(/1 pending answer/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /sync now/i }));
    expect(await screen.findByText(/all answers synced/i)).toBeInTheDocument();
  });

  it("shares the learner's public progress URL", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: share,
    });
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 3,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({
        display_name: "Ada",
        share_slug: "ada-learner",
        preferences: { meta_language: "eng" },
      } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);
    render(<Home />, { wrapper: MemoryRouter });
    await userEvent.click(
      await screen.findByRole("button", { name: /share my progress/i }),
    );
    expect(share).toHaveBeenCalledWith(
      expect.objectContaining({
        url: `${window.location.origin}/u/ada-learner`,
      }),
    );
  });

  it("copies the public progress URL when Web Share is unavailable", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 3,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({
        share_slug: "ada-learner",
        preferences: { meta_language: "eng" },
      } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);
    render(<Home />, { wrapper: MemoryRouter });
    await userEvent.click(
      await screen.findByRole("button", { name: /share my progress/i }),
    );
    expect(writeText).toHaveBeenCalledWith(
      `${window.location.origin}/u/ada-learner`,
    );
    expect(await screen.findByRole("status")).toHaveTextContent(/link copied/i);
  });
});
