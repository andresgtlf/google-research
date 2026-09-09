import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import { clearPersistedState } from "./lib/persist";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary
      area="the app"
      onReset={() => {
        // A render error can leave component state in an inconsistent
        // shape that a soft reset cannot reliably repair, so this clears
        // the persisted job pointers and does a full reload rather than
        // just re-rendering <App />. The job itself keeps running on the
        // server either way.
        clearPersistedState();
        window.location.reload();
      }}
    >
      <App />
    </ErrorBoundary>
  </StrictMode>
);
