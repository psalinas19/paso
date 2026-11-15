import { useEffect, useState } from "react";
import { loadConfig, type Taxonomy } from "../review/api";
import { cachedTaxonomy, taxonomyOnce } from "./bank";

/** The subjects' topics and error types: what was last fetched, refreshed once per visit. */
export function useTaxonomy(): Taxonomy[] {
  const [taxonomy, setTaxonomy] = useState(cachedTaxonomy);
  useEffect(() => {
    let alive = true;
    // Offline or not configured yet: the pickers show what was saved, or stay out of the way.
    taxonomyOnce(loadConfig()).then((fetched) => alive && setTaxonomy(fetched), () => {});
    return () => {
      alive = false;
    };
  }, []);
  return taxonomy;
}
