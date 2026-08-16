import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "../lib/api";
import { AdminContentDetailRoute, AdminContentList } from "./AdminContent";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});

const item = {
  id: 42,
  source_key: "ibo:proverb:test",
  language: "ibo",
  dialect: "central",
  category: "proverbs_work",
  content_type: "proverb",
  difficulty_level: "advanced",
  target_text: "Egbe bere ugo bere",
  target_text_toned: null,
  example_sentence: null,
  example_translation: null,
  audio_url: "https://example.test/audio.mp3",
  audio_state: "placeholder",
  status: "published",
  verified: false,
  verified_by: null,
  verified_by_name: null,
  verified_at: null,
  contributor_id: null,
  flag_count: 1,
  sort_order: 10,
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
} as const;

const emptyEnglish = {
  content_id: 42,
  meta_language: "eng",
  translation: "",
  literal_translation: null,
  cultural_note: "Existing note",
  verified: false,
  verified_by: null,
  verified_by_name: null,
  verified_at: null,
  contributor_id: null,
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
};

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/admin/content/42"]}>
      <Routes>
        <Route
          path="/admin/content/:contentId"
          element={<AdminContentDetailRoute />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdminContentList", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it.each([
    ["Unverified", "verified=false"],
    ["Flagged", "has_flags=true"],
    ["Missing Dutch translation", "missing_translation=nld"],
  ])("sends the %s daily queue filter", async (label, query) => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    render(<AdminContentList />, { wrapper: MemoryRouter });
    await screen.findByRole("heading", { name: /content management/i });

    await userEvent.click(screen.getByRole("button", { name: label }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenLastCalledWith(
        expect.stringContaining(query),
        { authenticated: true },
      ),
    );
  });
});

describe("AdminContentDetailRoute", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("distinguishes a missing translation from an existing blank one", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      item,
      translations: [
        { meta_language: "eng", state: emptyEnglish },
        { meta_language: "nld", state: null },
      ],
    });
    renderDetail();

    expect(
      await screen.findByText(/no dutch translation yet/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/english translation exists but is blank/i),
    ).toBeInTheDocument();
  });

  it("keeps identity fields read-only and renders every audio state", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ item, translations: [] });
    renderDetail();

    await screen.findByRole("heading", { name: /edit content/i });
    expect(screen.getByText(item.source_key)).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /source key/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /^language$/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /content type/i }),
    ).not.toBeInTheDocument();
    const audioState = screen.getByRole("combobox", { name: /audio state/i });
    expect(audioState).toHaveTextContent("Missing");
    expect(audioState).toHaveTextContent("Placeholder");
    expect(audioState).toHaveTextContent("Verified");
  });

  it("disables the inline player when audio state is missing despite a URL", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      item: { ...item, audio_state: "missing" },
      translations: [],
    });
    renderDetail();

    expect(
      await screen.findByRole("button", { name: /audio coming soon/i }),
    ).toBeDisabled();
    expect(document.querySelector("audio")).not.toBeInTheDocument();
  });

  it("requires a change note before saving", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ item, translations: [] });
    renderDetail();
    await screen.findByRole("heading", { name: /edit content/i });
    vi.mocked(apiFetch).mockClear();

    await userEvent.click(screen.getByRole("button", { name: /save item/i }));

    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows a proverb translation 422 verbatim without clearing typed work", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        item,
        translations: [{ meta_language: "nld", state: null }],
      })
      .mockRejectedValueOnce(
        new ApiError(422, "cultural_note is required for proverb translations"),
      );
    renderDetail();
    await userEvent.click(
      await screen.findByRole("button", { name: /create dutch translation/i }),
    );
    const translation = screen.getByRole("textbox", {
      name: /^dutch translation$/i,
    });
    await userEvent.type(translation, "Een spreekwoord");
    await userEvent.type(
      screen.getByRole("textbox", { name: /dutch change note/i }),
      "Add Dutch draft",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /save dutch translation/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "cultural_note is required for proverb translations",
    );
    expect(translation).toHaveValue("Een spreekwoord");
    expect(apiFetch).toHaveBeenLastCalledWith(
      "/v1/admin/content/42/translations/nld",
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("uses the verification target to update the returned resource", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        item,
        translations: [{ meta_language: "eng", state: emptyEnglish }],
      })
      .mockResolvedValueOnce({
        target: "translation",
        content: null,
        translation: {
          ...emptyEnglish,
          verified: true,
          verified_by: "reviewer-1",
          verified_by_name: "Reviewer",
          verified_at: "2026-08-16T12:00:00Z",
        },
      });
    renderDetail();
    await userEvent.type(
      await screen.findByRole("textbox", { name: /item change note/i }),
      "Review translation",
    );

    await userEvent.click(screen.getByRole("button", { name: /verify item/i }));

    expect(
      await screen.findByText(/verified by reviewer/i),
    ).toBeInTheDocument();
  });
});
