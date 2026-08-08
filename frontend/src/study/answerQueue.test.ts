import { describe, expect, it, vi } from "vitest";
import { AnswerQueue } from "./answerQueue";

const answer = (id: number) => ({
  content_id: id,
  correct: true,
  mode: "flashcard" as const,
  duration_ms: 42,
});

describe("AnswerQueue", () => {
  it("generates a client answer id and auto-submits at 20", async () => {
    const send = vi.fn().mockResolvedValue({
      results: Array.from({ length: 20 }, (_, i) => ({
        client_answer_id: `id-${i}`,
        status: "accepted",
      })),
      current_streak: 2,
      today_xp: 20,
    });
    const ids = Array.from({ length: 20 }, (_, i) => `id-${i}`);
    const queue = new AnswerQueue(send, () => ids.shift()!);
    for (let i = 0; i < 20; i++) await queue.add(answer(i));
    expect(send).toHaveBeenCalledOnce();
    expect(send.mock.calls[0][0][0]).toMatchObject({
      client_answer_id: "id-0",
      content_id: 0,
    });
    expect(queue.pending).toHaveLength(0);
    expect(queue.latestResponse?.today_xp).toBe(20);
  });

  it.each(["accepted", "duplicate", "unknown_content", "id_conflict"] as const)(
    "clears a %s result",
    async (status) => {
      const send = vi.fn().mockResolvedValue({
        results: [{ client_answer_id: "fixed", status }],
        current_streak: 1,
        today_xp: 1,
      });
      const queue = new AnswerQueue(send, () => "fixed");
      await queue.add(answer(1));
      await queue.flush();
      expect(queue.pending).toHaveLength(0);
    },
  );

  it("preserves answers when submission fails", async () => {
    const queue = new AnswerQueue(
      vi.fn().mockRejectedValue(new Error("offline")),
      () => "fixed",
    );
    await queue.add(answer(1));
    await expect(queue.flush()).rejects.toThrow("offline");
    expect(queue.pending).toHaveLength(1);
  });

  it("clears by content id when the schema returns a null client id", async () => {
    const send = vi
      .fn()
      .mockResolvedValue({
        results: [
          { content_id: 7, client_answer_id: null, status: "unknown_content" },
        ],
        current_streak: 0,
        today_xp: 0,
      });
    const queue = new AnswerQueue(send, () => "answer-7");
    await queue.add(answer(7));
    await queue.flush();
    expect(queue.pending).toHaveLength(0);
  });
});
