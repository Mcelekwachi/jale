import type { StudyMode } from "../lib/types";

export interface PendingAnswer {
  content_id: number;
  correct: boolean;
  mode: StudyMode;
  duration_ms: number | null;
  client_answer_id: string;
}
export type NewAnswer = Omit<PendingAnswer, "client_answer_id">;
export interface AnswerResponse {
  results: {
    content_id: number;
    client_answer_id: string | null;
    status: "accepted" | "duplicate" | "unknown_content" | "id_conflict";
  }[];
  current_streak: number;
  today_xp: number;
}

export class AnswerQueue {
  pending: PendingAnswer[] = [];
  latestResponse: AnswerResponse | null = null;
  constructor(
    private send: (answers: PendingAnswer[]) => Promise<AnswerResponse>,
    private uuid: () => string = () => crypto.randomUUID(),
  ) {}
  async add(answer: NewAnswer) {
    this.pending.push({ ...answer, client_answer_id: this.uuid() });
    if (this.pending.length >= 20) return this.flush();
  }
  async flush() {
    if (!this.pending.length) return null;
    const response = await this.send([...this.pending]);
    this.latestResponse = response;
    const clearedIds = new Set(
      response.results.map((result) => result.client_answer_id).filter(Boolean),
    );
    const clearedContent = new Set(
      response.results
        .filter((result) => result.client_answer_id === null)
        .map((result) => result.content_id),
    );
    for (const result of response.results)
      if (result.status === "id_conflict")
        console.warn("Study answer id conflict", result.client_answer_id);
    this.pending = this.pending.filter(
      (answer) =>
        !clearedIds.has(answer.client_answer_id) &&
        !clearedContent.has(answer.content_id),
    );
    return response;
  }
}
