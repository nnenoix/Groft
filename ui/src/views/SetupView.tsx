import { useState } from "react";

export type CliDetectResult = {
  installed: boolean;
  path: string | null;
  version: string | null;
};

type Props = {
  detect: CliDetectResult;
  onRecheck: () => Promise<void> | void;
};

/// First-run installer shell. Full step runner (terminal stream + right-hand
/// step list) lands in 2C; for now the routing in App.tsx has a concrete
/// component to render, and the Recheck button lets a user bypass setup
/// once they've installed claude manually in another terminal.
export function SetupView({ detect, onRecheck }: Props) {
  const [rechecking, setRechecking] = useState(false);
  async function handleRecheck() {
    setRechecking(true);
    try {
      await onRecheck();
    } finally {
      setRechecking(false);
    }
  }

  return (
    <div className="setup-view">
      <div className="setup-view__body">
        <h1>Groft — First-run setup</h1>
        <p>
          The <code>claude</code> CLI is required but was not found on this
          machine. The guided installer will land in the next commit — for
          now, install it yourself and click <b>Recheck</b>.
        </p>
        <pre className="setup-view__snippet">
{`npm install -g @anthropic-ai/claude-code
claude --version
claude   # first run opens a browser for OAuth`}
        </pre>
        <button
          type="button"
          onClick={handleRecheck}
          disabled={rechecking}
        >
          {rechecking ? "Checking…" : "Recheck"}
        </button>
        <details className="setup-view__debug">
          <summary>Detection result</summary>
          <pre>{JSON.stringify(detect, null, 2)}</pre>
        </details>
      </div>
    </div>
  );
}
