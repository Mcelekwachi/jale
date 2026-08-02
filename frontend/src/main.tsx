import { getEnvironment } from "./lib/env";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Frontend root element is missing");
const root: HTMLElement = rootElement;

function showStartupError(error: unknown): void {
  const message =
    error instanceof Error ? error.message : "The frontend could not start";
  const container = document.createElement("main");
  container.className = "startup-error";
  const heading = document.createElement("h1");
  heading.textContent = "Jalɛ could not start";
  const detail = document.createElement("p");
  detail.textContent = message;
  const help = document.createElement("p");
  help.textContent = "Check frontend environment configuration and reload.";
  container.append(heading, detail, help);
  root.replaceChildren(container);
}

try {
  getEnvironment();
  void import("./bootstrap")
    .then(({ bootstrap }) => bootstrap(root))
    .catch(showStartupError);
} catch (error) {
  showStartupError(error);
}
