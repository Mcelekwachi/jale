import { getEnvironment } from "./lib/env";
import { getUiStrings } from "./i18n/useUiStrings";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Frontend root element is missing");
const root: HTMLElement = rootElement;

function showStartupError(error: unknown): void {
  const strings = getUiStrings().shared;
  const message = error instanceof Error ? error.message : strings.startupError;
  const container = document.createElement("main");
  container.className = "startup-error";
  const heading = document.createElement("h1");
  heading.textContent = strings.startupHeading;
  const detail = document.createElement("p");
  detail.textContent = message;
  const help = document.createElement("p");
  help.textContent = strings.startupHelp;
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
