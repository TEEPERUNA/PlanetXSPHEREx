import { useEffect, useState } from "react";
import { getGaia, type GaiaStar } from "../../api";
import { fieldRadiusArcsec } from "../lib/gaiaField";
import type { Meta } from "../types";

export interface GaiaFieldState {
  status: "loading" | "ok" | "error";
  stars: GaiaStar[];
  truncated: boolean;
}

// All Gaia DR3 stars around the image, from the backend (GET /api/gaia). One request per field;
// the backend caches it. On failure the viewer just shows the target star as before.
export function useGaiaField(meta: Meta): GaiaFieldState {
  const { ra_deg, dec_deg } = meta;
  const radius = fieldRadiusArcsec(meta);
  const [state, setState] = useState<GaiaFieldState>({ status: "loading", stars: [], truncated: false });

  useEffect(() => {
    const ctl = new AbortController();
    setState({ status: "loading", stars: [], truncated: false });
    getGaia(ra_deg, dec_deg, radius, ctl.signal)
      .then((r) => setState({ status: "ok", stars: r.stars, truncated: r.truncated }))
      .catch(() => {
        if (!ctl.signal.aborted) setState({ status: "error", stars: [], truncated: false });
      });
    return () => ctl.abort();
  }, [ra_deg, dec_deg, radius]);

  return state;
}
