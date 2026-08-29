import { apiFetch } from "../lib/api";
import { AnswerQueue, type AnswerResponse } from "./answerQueue";

export const answerQueue = new AnswerQueue((answers) =>
  apiFetch<AnswerResponse>("/v1/study/answers", {
    method: "POST",
    authenticated: true,
    body: JSON.stringify({
      answers: answers.map(({ queued_at, ...answer }) => {
        void queued_at;
        return answer;
      }),
    }),
  }),
);

export function startAnswerQueueLifecycle(): () => void {
  const flush = () => void answerQueue.flush().catch(() => undefined);
  flush();
  window.addEventListener("online", flush);
  return () => window.removeEventListener("online", flush);
}
