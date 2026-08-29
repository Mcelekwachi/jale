import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { startAnswerQueueLifecycle } from "./study/answerQueueService";
import "./index.css";

export function bootstrap(root: HTMLElement) {
  startAnswerQueueLifecycle();
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
