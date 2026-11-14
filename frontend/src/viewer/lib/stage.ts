// Backend stage name -> text for the user.
// The quick preview run adds a "preview_" prefix, e.g. "preview_downloading".

const LABELS: Record<string, string> = {
  queued: "Waiting in queue",
  downloading: "Downloading SPHEREx images",
  processing: "Processing images",
  done: "Finishing",
};

export function describeStage(stage: string): { label: string; isPreview: boolean } {
  const isPreview = stage.startsWith("preview_");
  const base = isPreview ? stage.slice("preview_".length) : stage;
  const label = LABELS[base] ?? base.replace(/_/g, " ");
  return { label, isPreview };
}

// Show a filled bar only while the count is still moving.
// done === total while still loading means "working, no count", so the bar is indeterminate.
export function hasCount(done: number, total: number): boolean {
  return total > 0 && done < total;
}
