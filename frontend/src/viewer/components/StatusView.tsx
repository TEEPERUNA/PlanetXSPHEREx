import { describeStage, hasCount } from "../lib/stage";
import type { ViewerStatus } from "../types";

interface ProgressProps {
  stage: string;
  done: number;
  total: number;
}

// Stage text + progress bar. Also used above the quick preview.
export function LoadingProgress({ stage, done, total }: ProgressProps) {
  const { label } = describeStage(stage);
  const counting = hasCount(done, total);
  return (
    <div className="progress" role="status" aria-live="polite">
      <p className="progress__label">
        {label}
        {counting ? ` ${done}/${total}` : "…"}
      </p>
      {/* No value = indeterminate bar */}
      {counting ? <progress value={done} max={total} /> : <progress />}
    </div>
  );
}

interface Props {
  status: Exclude<ViewerStatus, { kind: "done" }>;
  onRetry?: () => void;
}

// Empty, loading and error states.
export function StatusView({ status, onRetry }: Props) {
  if (status.kind === "empty") {
    return (
      <div className="status">
        <p>Pick a target or enter coordinates to see SPHEREx images.</p>
      </div>
    );
  }

  if (status.kind === "loading") {
    const { isPreview } = describeStage(status.stage);
    return (
      <div className="status">
        <p>Loading SPHEREx images</p>
        <LoadingProgress stage={status.stage} done={status.done} total={status.total} />
        <p className="status__hint">
          {isPreview
            ? "A quick preview comes first, then the full data."
            : "A new position can take a few minutes."}
        </p>
      </div>
    );
  }

  return (
    <div className="status status--error" role="alert">
      <p>Could not load images.</p>
      <p className="status__message">{status.message}</p>
      {onRetry && (
        <button type="button" className="primary status__retry" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
