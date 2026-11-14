import type { ViewerStatus } from "../types";

interface Props {
  status: Exclude<ViewerStatus, { kind: "done" }>;
}

// Empty, loading and error states.
export function StatusView({ status }: Props) {
  if (status.kind === "empty") {
    return (
      <div className="status">
        <p>Pick a target or click the sky map to see SPHEREx images.</p>
      </div>
    );
  }

  if (status.kind === "loading") {
    const hasProgress = status.total > 0;
    return (
      <div className="status" role="status" aria-live="polite">
        <p>Loading SPHEREx images: {status.stage}</p>
        {hasProgress && (
          <>
            <progress value={status.done} max={status.total} />
            <p className="status__count">
              {status.done}/{status.total}
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="status status--error" role="alert">
      <p>Could not load images.</p>
      <p className="status__message">{status.message}</p>
    </div>
  );
}
