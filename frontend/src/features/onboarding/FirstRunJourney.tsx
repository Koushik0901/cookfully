import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, KitchenCompanion } from "../../components";
import { RecipeImportDialog } from "../recipes/RecipeImportDialog";
import { onboardingApi } from "./api";
import type { OnboardingAction, OnboardingState } from "./types";

export function FirstRunJourney({ onboarding }: { onboarding: OnboardingState }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const resolve = useMutation({
    mutationFn: onboardingApi.resolve,
  });

  async function choose(action: OnboardingAction, destination: string) {
    try {
      await resolve.mutateAsync({ state: "completed", firstAction: action, version: onboarding.version });
    } catch {
      // The mutation retains the error for diagnostics; onboarding remains non-blocking.
    } finally {
      // Optional guidance must never block the real task if preference persistence fails.
      navigate(destination);
    }
  }

  async function dismiss() {
    try {
      const value = await resolve.mutateAsync({ state: "dismissed", version: onboarding.version });
      queryClient.setQueryData(["owner-onboarding"], value);
      setDismissed(true);
    } catch {
      // Keep the surface visible with its inline recovery message.
    }
  }

  if (dismissed) return null;

  return (
    <section className="first-run" aria-labelledby="first-run-title">
      <div className="first-run__illustration">
        <KitchenCompanion moment="empty" size="lg" />
        <p>Recipes first. Guidance when it is useful.</p>
      </div>
      <div className="first-run__content">
        <div className="first-run__topline">
          <p className="eyebrow">Your recipe library</p>
          <Button variant="ghost" onClick={() => void dismiss()} disabled={resolve.isPending}>Skip welcome</Button>
        </div>
        <h1 id="first-run-title">Start with a recipe you already love.</h1>
        <p>Write it from memory or bring it in from the web. Cookfully will keep the ingredients, method, and nutrition estimate together.</p>
        <div className="first-run__actions">
          <Button onClick={() => void choose("manual_recipe", "/app/recipes/new")} disabled={resolve.isPending}>Write a recipe</Button>
          <RecipeImportDialog
            trigger={<Button variant="secondary" disabled={resolve.isPending}>Import from the web</Button>}
            onImported={() => resolve.mutateAsync({ state: "completed", firstAction: "import_recipe", version: onboarding.version })}
          />
        </div>
        <div className="first-run__secondary-actions">
          <Button variant="ghost" onClick={() => void choose("view_plan", "/app/plan")} disabled={resolve.isPending}>Explore the weekly planner <ArrowRight aria-hidden="true" /></Button>
        </div>
        {resolve.error instanceof Error ? <p className="error-text" role="alert">Your choice could not be saved. You can still use the kitchen normally.</p> : null}
      </div>
    </section>
  );
}
