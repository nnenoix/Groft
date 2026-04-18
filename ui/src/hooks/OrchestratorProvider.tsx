import { createContext, useContext, type ReactNode } from "react";
import useOrchestrator, { type UseOrchestratorResult } from "./useOrchestrator";

const OrchestratorContext = createContext<UseOrchestratorResult | null>(null);

export function OrchestratorProvider({ children }: { children: ReactNode }) {
  const value = useOrchestrator();
  return (
    <OrchestratorContext.Provider value={value}>
      {children}
    </OrchestratorContext.Provider>
  );
}

export function useOrchestratorContext(): UseOrchestratorResult {
  const ctx = useContext(OrchestratorContext);
  if (!ctx) throw new Error("useOrchestratorContext must be used within OrchestratorProvider");
  return ctx;
}
