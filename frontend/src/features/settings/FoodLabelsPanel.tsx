import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tags } from "lucide-react";

import { Button } from "../../components";
import { foodLabelsApi } from "./api";

const QUERY_KEY = ["food-label-summary"];

/** Progress and a start action for labelling USDA foods with decision models. */
export function FoodLabelsPanel({ enabled }: { enabled: boolean }) {
  const queryClient = useQueryClient();
  const summary = useQuery({
    queryKey: QUERY_KEY,
    queryFn: foodLabelsApi.summary,
    refetchInterval: (query) => (query.state.data?.pollAfterSeconds ? query.state.data.pollAfterSeconds * 1000 : false),
  });
  const run = useMutation({
    mutationFn: foodLabelsApi.run,
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: QUERY_KEY }); },
  });
  const data = summary.data;
  const busy = Boolean(data && (data.active || data.waiting));
  const percent = data && data.total ? Math.round((data.labelled / data.total) * 100) : 0;
  return (
    <div className="food-labels-panel" aria-live="polite">
      <div>
        <strong>Food labels</strong>
        {summary.isPending ? <p className="muted">Checking label coverage…</p> : null}
        {summary.isError ? <p className="error-text">Label coverage could not be loaded.</p> : null}
        {data ? (
          <p className="muted">
            {data.total ? `${data.labelled.toLocaleString()} of ${data.total.toLocaleString()} USDA foods labelled (${percent}%).` : "Install USDA reference data first."}
            {busy ? " Labelling now…" : ""}
          </p>
        ) : null}
        {data && data.total ? <progress max={data.total} value={data.labelled} aria-label="Food labelling progress" /> : null}
        {run.error instanceof Error ? <p className="error-text" role="alert">{run.error.message}</p> : null}
      </div>
      <Button type="button" variant="secondary" disabled={!enabled || busy || run.isPending || !data?.total} onClick={() => run.mutate()}>
        <Tags aria-hidden="true" /> {busy ? "Labelling…" : "Label foods now"}
      </Button>
    </div>
  );
}
