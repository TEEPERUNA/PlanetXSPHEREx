import { useEffect, useState } from "react";
import { joinUrl } from "../lib/frames";
import { detectSources, type Source } from "../lib/gaiaField";
import type { Band, Meta } from "../types";
import { loadFits, pathForEpoch } from "./usePixelValues";

// Point sources in the epoch stack on screen (outputs[band].fits), or in `stackPath` when given
// (the deep image's combined_fits). Empty when there is no stack.
export function useSources(meta: Meta, baseUrl: string, band: Band, epoch: number | null, stackPath?: string): Source[] {
  const path = stackPath ?? (epoch === null ? undefined : pathForEpoch(meta.outputs[band]?.fits, epoch));
  const url = path ? joinUrl(baseUrl, path) : null;
  const [found, setFound] = useState<{ url: string; sources: Source[] } | null>(null);

  useEffect(() => {
    if (!url) return;
    let alive = true;
    loadFits(url)
      .then((images) => alive && setFound({ url, sources: images[0] ? detectSources(images[0]) : [] }))
      .catch(() => alive && setFound({ url, sources: [] }));
    return () => {
      alive = false;
    };
  }, [url]);

  return found && found.url === url ? found.sources : [];
}
