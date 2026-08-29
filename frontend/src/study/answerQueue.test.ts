import { deleteDB } from "idb";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnswerQueue } from "./answerQueue";

const answer = (id: number) => ({
  content_id: id,
  correct: true,
  mode: "flashcard" as const,
  duration_ms: 42,
});

describe("AnswerQueue", () => {
  afterEach(async () => {
    await deleteDB("jale");
  });

  it("persists an answer before making the twentieth-item network call", async () => {
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
    for (let i = 0; i < 19; i++) await queue.add(answer(i));
    send.mockImplementationOnce(async (answers) => {
      expect(await queue.list()).toHaveLength(20);
      return {
        results: answers.map((pending: { client_answer_id: string }) => ({
          content_id: 1,
          client_answer_id: pending.client_answer_id,
          status: "accepted" as const,
        })),
        current_streak: 2,
        today_xp: 20,
      };
    });
    await queue.add(answer(19));
    expect(send).toHaveBeenCalledOnce();
    expect(await queue.count()).toBe(0);
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
      expect(await queue.count()).toBe(0);
    },
  );

  it("preserves answers when submission fails", async () => {
    const queue = new AnswerQueue(
      vi.fn().mockRejectedValue(new Error("offline")),
      () => "fixed",
    );
    await queue.add(answer(1));
    await expect(queue.flush()).rejects.toThrow("offline");
    expect(await queue.count()).toBe(1);
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
    expect(await queue.count()).toBe(0);
  });

  it("does not send the same answer twice during overlapping flushes", async () => {
    let release!: (response: {
      results: { content_id: number; client_answer_id: string; status: "accepted" }[];
      current_streak: number;
      today_xp: number;
    }) => void;
    const send = vi.fn(
      () =>
        new Promise<{
          results: { content_id: number; client_answer_id: string; status: "accepted" }[];
          current_streak: number;
          today_xp: number;
        }>((resolve) => {
          release = resolve;
        }),
    );
    const queue = new AnswerQueue(send, () => "fixed");
    await queue.add(answer(1));
    const first = queue.flush();
    const second = queue.flush();
    await vi.waitFor(() => expect(send).toHaveBeenCalledOnce());
    release({
      results: [
        { content_id: 1, client_answer_id: "fixed", status: "accepted" },
      ],
      current_streak: 1,
      today_xp: 1,
    });
    await Promise.all([first, second]);
    expect(send).toHaveBeenCalledOnce();
  });

  it("caps the queue at the oldest 500 answers", async () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    let nextId = 0;
    const queue = new AnswerQueue(vi.fn(), () => `id-${nextId++}`, Infinity);
    for (let i = 0; i < 501; i++) await queue.add(answer(i));
    const records = await queue.list();
    expect(records).toHaveLength(500);
    expect(records[0].content_id).toBe(0);
    expect(records[499].content_id).toBe(499);
    expect(warning).toHaveBeenCalledOnce();
  });
});
