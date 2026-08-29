import { describe, expect, it, vi } from "vitest";

import { answerQueue, startAnswerQueueLifecycle } from "./answerQueueService";

describe("answer queue lifecycle", () => {
  it("flushes on app start and whenever the browser comes online", async () => {
    const flush = vi.spyOn(answerQueue, "flush").mockResolvedValue(null);
    const stop = startAnswerQueueLifecycle();
    expect(flush).toHaveBeenCalledOnce();
    window.dispatchEvent(new Event("online"));
    expect(flush).toHaveBeenCalledTimes(2);
    stop();
    window.dispatchEvent(new Event("online"));
    expect(flush).toHaveBeenCalledTimes(2);
  });
});
