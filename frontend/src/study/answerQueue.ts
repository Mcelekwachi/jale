import { openDB, type DBSchema, type IDBPObjectStore } from "idb";

import type { StudyMode } from "../lib/types";

const DATABASE_NAME = "jale";
const STORE_NAME = "answer_queue";
const MAX_ANSWERS = 500;

export interface PendingAnswer {
  content_id: number;
  correct: boolean;
  mode: StudyMode;
  duration_ms: number | null;
  client_answer_id: string;
  queued_at: number;
}

export type NewAnswer = Omit<PendingAnswer, "client_answer_id" | "queued_at">;

export interface AnswerResponse {
  results: {
    content_id: number;
    client_answer_id: string | null;
    status: "accepted" | "duplicate" | "unknown_content" | "id_conflict";
  }[];
  current_streak: number;
  today_xp: number;
}

interface JaleDatabase extends DBSchema {
  answer_queue: {
    key: string;
    value: PendingAnswer;
  };
}

async function withStore<T>(
  mode: IDBTransactionMode,
  operation: (
    store: IDBPObjectStore<
      JaleDatabase,
      ["answer_queue"],
      "answer_queue",
      IDBTransactionMode
    >,
  ) => Promise<T>,
): Promise<T> {
  const database = await openDB<JaleDatabase>(DATABASE_NAME, 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME))
        db.createObjectStore(STORE_NAME, { keyPath: "client_answer_id" });
    },
  });
  try {
    const transaction = database.transaction(STORE_NAME, mode);
    const result = await operation(transaction.objectStore(STORE_NAME));
    await transaction.done;
    return result;
  } finally {
    database.close();
  }
}

function notifyQueueChanged(count: number): void {
  window.dispatchEvent(
    new CustomEvent("jale:answer-queue-changed", { detail: { count } }),
  );
}

export class AnswerQueue {
  latestResponse: AnswerResponse | null = null;
  private activeFlush: Promise<AnswerResponse | null> | null = null;

  constructor(
    private send: (answers: PendingAnswer[]) => Promise<AnswerResponse>,
    private uuid: () => string = () => crypto.randomUUID(),
    private autoFlushAt = 20,
  ) {}

  async list(): Promise<PendingAnswer[]> {
    const answers = await withStore("readonly", (store) => store.getAll());
    return answers.sort(
      (left, right) =>
        left.queued_at - right.queued_at ||
        left.client_answer_id.localeCompare(right.client_answer_id),
    );
  }

  count(): Promise<number> {
    return withStore("readonly", (store) => store.count());
  }

  async add(answer: NewAnswer): Promise<AnswerResponse | null | undefined> {
    const count = await this.count();
    if (count >= MAX_ANSWERS) {
      console.warn("Study answer queue is full; keeping the oldest 500 answers");
      return;
    }
    await withStore("readwrite", (store) =>
      store.put!({
        ...answer,
        client_answer_id: this.uuid(),
        queued_at: Date.now(),
      }),
    );
    const nextCount = count + 1;
    notifyQueueChanged(nextCount);
    if (nextCount % this.autoFlushAt === 0) return this.flush();
  }

  flush(): Promise<AnswerResponse | null> {
    if (this.activeFlush) return this.activeFlush;
    this.activeFlush = this.performFlush().finally(() => {
      this.activeFlush = null;
    });
    return this.activeFlush;
  }

  private async performFlush(): Promise<AnswerResponse | null> {
    const pending = await this.list();
    if (!pending.length) return null;
    const response = await this.send(pending);
    this.latestResponse = response;
    const clearedIds = new Set(
      response.results
        .map((result) => result.client_answer_id)
        .filter((id): id is string => Boolean(id)),
    );
    const clearedContent = new Set(
      response.results
        .filter((result) => result.client_answer_id === null)
        .map((result) => result.content_id),
    );
    for (const result of response.results)
      if (result.status === "id_conflict")
        console.warn("Study answer id conflict", result.client_answer_id);
    await withStore("readwrite", async (store) => {
      for (const answer of pending)
        if (
          clearedIds.has(answer.client_answer_id) ||
          clearedContent.has(answer.content_id)
        )
          await store.delete!(answer.client_answer_id);
    });
    notifyQueueChanged(await this.count());
    return response;
  }
}
