import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./index.css";

export function bootstrap(root: HTMLElement) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
