import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AgentStoreProvider } from "./store/agentStore";
import { OrchestratorProvider } from "./hooks/OrchestratorProvider";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AgentStoreProvider>
      <OrchestratorProvider>
        <App />
      </OrchestratorProvider>
    </AgentStoreProvider>
  </React.StrictMode>,
);
