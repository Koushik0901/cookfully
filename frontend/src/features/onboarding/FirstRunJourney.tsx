import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, KitchenCompanion } from "../../components";
import { referenceDataApi } from "../referenceData/api";
import { RecipeImportDialog } from "../recipes/RecipeImportDialog";
import { onboardingApi } from "./api";
import type { OnboardingAction, OnboardingState, ReferenceDataChoice } from "./types";

export function FirstRunJourney({ onboarding }: { onboarding: OnboardingState }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const [step, setStep] = useState<"welcome" | "nutrition">("welcome");
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

  async function chooseNutrition(choice: ReferenceDataChoice) {
    try {
      await resolve.mutateAsync({
        state: "completed",
        referenceDataChoice: choice,
        version: onboarding.version,
      });
    } catch {
      // The mutation retains the error for diagnostics; onboarding remains non-blocking.
    }
    if (choice !== "none") {
      const datasets =
        choice === "both"
          ? (["foundation_sr_legacy", "branded"] as const)
          : (["foundation_sr_legacy"] as const);
      try {
        await referenceDataApi.install([...datasets]);
      } catch {
        // Install failures never block the kitchen; Settings shows the retry surface.
      }
    }
    navigate("/app/recipes");
  }

  if (dismissed) return null;

  if (step === "nutrition") {
    return (
      <section className="first-run" aria-labelledby="nutrition-step-title">
        <div className="first-run__illustration">
          <KitchenCompanion moment="empty" size="lg" />
          <p>Real macros come from real food data.</p>
        </div>
        <div className="first-run__content">
          <div className="first-run__topline">
            <p className="eyebrow">Nutrition reference data</p>
            <Button variant="ghost" onClick={() => setStep("welcome")} disabled={resolve.isPending}>Back</Button>
          </div>
          <h1 id="nutrition-step-title">Real nutrition numbers?</h1>
          <p>Cookfully estimates macros from the USDA food database. Pick what to install — the app downloads and sets it up in the background while you cook.</p>
          <div className="first-run__actions first-run__actions--stacked">
            <button type="button" className="option-card" onClick={() => void chooseNutrition("both")} disabled={resolve.isPending}>
              <strong>Install both <span className="badge">Recommended</span></strong>
              <span>Foundation + SR Legacy (~10,000 foods, ~100 MB) and Branded gym products (~1.5 GB).</span>
            </button>
            <button type="button" className="option-card" onClick={() => void chooseNutrition("foundation_sr_legacy")} disabled={resolve.isPending}>
              <strong>Foundation + SR Legacy only</strong>
              <span>Whole foods and ingredients — everything most home cooks use. ~100 MB.</span>
            </button>
            <button type="button" className="option-card" onClick={() => void chooseNutrition("none")} disabled={resolve.isPending}>
              <strong>Not now</strong>
              <span>You can install this later from Settings → Nutrition data.</span>
            </button>
          </div>
          {resolve.error instanceof Error ? <p className="error-text" role="alert">Your choice could not be saved. You can still use the kitchen normally.</p> : null}
        </div>
      </section>
    );
  }

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
          <Button variant="ghost" onClick={() => setStep("nutrition")} disabled={resolve.isPending}>Set up nutrition data <ArrowRight aria-hidden="true" /></Button>
          <Button variant="ghost" onClick={() => void choose("view_plan", "/app/plan")} disabled={resolve.isPending}>Explore the weekly planner <ArrowRight aria-hidden="true" /></Button>
        </div>
        {resolve.error instanceof Error ? <p className="error-text" role="alert">Your choice could not be saved. You can still use the kitchen normally.</p> : null}
      </div>
    </section>
  );
}
