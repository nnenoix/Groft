import { useOrchestratorContext } from "../hooks/OrchestratorProvider";
import { Composer as ComposerPrimitive } from "./primitives";

interface ComposerProps {
  placeholder?: string;
  compact?: boolean;
}

function Composer({ placeholder, compact }: ComposerProps) {
  const { sendMessage } = useOrchestratorContext();
  return (
    <ComposerPrimitive
      placeholder={placeholder}
      compact={compact}
      onSubmit={({ text, mode, model }) => {
        sendMessage({ type: "message", from: "ui", to: "opus", content: text, mode, model });
      }}
    />
  );
}

export default Composer;
