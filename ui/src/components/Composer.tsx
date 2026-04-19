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
      onSubmit={({ text, mode, model, files }) => {
        const attachments = files.map((f) => ({
          name: f.name,
          size: f.size,
          ...(f.path !== undefined ? { path: f.path } : {}),
        }));
        sendMessage({
          type: "message",
          from: "ui",
          to: "opus",
          content: text,
          mode,
          model,
          ...(attachments.length > 0 ? { attachments } : {}),
        });
      }}
    />
  );
}

export default Composer;
