import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AgentStoreProvider } from "./store/agentStore";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AgentStoreProvider>
      <App />
    </AgentStoreProvider>
  </React.StrictMode>,
);
