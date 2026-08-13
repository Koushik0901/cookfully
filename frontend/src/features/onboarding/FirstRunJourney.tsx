import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, CalendarDays, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../components";
import { RecipeImportDialog } from "../recipes/RecipeImportDialog";
import { onboardingApi } from "./api";
import type { OnboardingAction } from "./types";

const FIRST_STEPS: Array<{
  action: OnboardingAction;
  title: string;
  body: string;
  Icon: typeof BookOpenText;
}> = [
  {
    action: "manual_recipe",
    title: "Write a recipe you know",
    body: "Start with dinner from memory, a notebook, or someone you love cooking for.",
    Icon: BookOpenText,
  },
  {
    action: "import_recipe",
    title: "Bring in a web recipe",
    body: "Save a recipe you already trust and keep its ingredients, method, and estimate together.",
    Icon: ArrowRight,
  },
  {
    action: "view_plan",
    title: "See your week",
    body: "Explore the planner first. A nutrition guide is there when you want it, never in the way.",
    Icon: CalendarDays,
  },
];

export function FirstRunJourney() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const onboarding = useQuery({ queryKey: ["owner-onboarding"], queryFn: onboardingApi.get, retry: 1 });
  const resolve = useMutation({
    mutationFn: onboardingApi.resolve,
    onSuccess: (value) => queryClient.setQueryData(["owner-onboarding"], value),
  });

  function choose(action: OnboardingAction) {
    if (!onboarding.data) return;
    resolve.mutate({ state: "completed", firstAction: action, version: onboarding.data.version });
    if (action === "manual_recipe") navigate("/app/recipes/new");
    if (action === "view_plan") navigate("/app/plan");
  }

  // The welcome guide is optional. Do not let a preferences read claim space
  // or interrupt an established kitchen while it resolves or retries.
  if (onboarding.isPending || onboarding.isError) return null;
  if (onboarding.data?.state !== "pending") return null;

  return (
    <section className="first-run" aria-labelledby="first-run-title">
      <div className="first-run__heading">
        <div>
          <p className="eyebrow">A calmer way to begin</p>
          <h1 id="first-run-title">Start with the food you already know.</h1>
          <p>You do not need a diet label, body measurements, or a perfect plan. Save one useful recipe, then let the week take shape around real life.</p>
        </div>
        <Button className="button--text" onClick={() => resolve.mutate({ state: "dismissed", version: onboarding.data.version })} disabled={resolve.isPending}>
          <X aria-hidden="true" />Skip for now
        </Button>
      </div>
      <div className="first-run__steps">
        {FIRST_STEPS.map(({ action, title, body, Icon }) => {
          const trigger = <Button className="button--secondary" onClick={() => choose(action)} disabled={resolve.isPending}>Choose this <ArrowRight aria-hidden="true" /></Button>;
          return (
            <article key={action} className="first-run__step">
              <Icon aria-hidden="true" />
              <div><h2>{title}</h2><p>{body}</p></div>
              {action === "import_recipe" ? <RecipeImportDialog trigger={trigger} /> : trigger}
            </article>
          );
        })}
      </div>
      {resolve.error instanceof Error ? <p className="error-text" role="alert">{resolve.error.message}</p> : null}
    </section>
  );
}
