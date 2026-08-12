import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button, DecimalInput, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { recipesApi } from "./api";
import type { RecipeWrite } from "./types";

const decimalPattern = /^(?!0(?:\.0{1,3})?$)(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?$/;

export function RecipeEditorPage() {
  const { recipeId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["recipe", recipeId], queryFn: () => recipesApi.get(recipeId!), enabled: Boolean(recipeId), retry: 1 });
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [yieldQuantity, setYieldQuantity] = useState("1.000");
  const [yieldUnit, setYieldUnit] = useState("servings");
  const [ingredients, setIngredients] = useState("");
  const [instructions, setInstructions] = useState("");
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!detail.data) return;
    setTitle(detail.data.title);
    setDescription(detail.data.description ?? "");
    setSourceUrl(detail.data.sourceUrl ?? "");
    setYieldQuantity(detail.data.yieldQuantity);
    setYieldUnit(detail.data.yieldUnit);
    setIngredients(detail.data.ingredients.map((item) => item.originalText).join("\n"));
    setInstructions(detail.data.instructions.join("\n"));
    setExtrasOpen(Boolean(detail.data.description || detail.data.sourceUrl));
  }, [detail.data]);

  const save = useMutation({
    mutationFn: (value: RecipeWrite) => recipeId && detail.data ? recipesApi.update(recipeId, detail.data.version, value) : recipesApi.create(value),
    onSuccess: (saved) => {
      if ("ingredients" in saved) queryClient.setQueryData(["recipe", saved.id], saved);
      else queryClient.removeQueries({ queryKey: ["recipe", saved.id], exact: true });
      void queryClient.invalidateQueries({ queryKey: ["recipes"] });
      navigate(`/app/recipes/${saved.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (!title.trim()) nextErrors.title = "Recipe title is required.";
    if (!decimalPattern.test(yieldQuantity)) nextErrors.yieldQuantity = "Use a positive value with up to three decimal places (and no exponent).";
    const ingredientLines = ingredients.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!ingredientLines.length) nextErrors.ingredients = "Enter at least one ingredient.";
    if (sourceUrl) {
      try { new URL(sourceUrl); } catch { nextErrors.sourceUrl = "Enter a complete source URL."; }
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    save.mutate({
      title: title.trim(),
      description: description.trim() || null,
      sourceUrl: sourceUrl.trim() || null,
      yieldQuantity,
      yieldUnit: yieldUnit.trim() || "servings",
      ingredients: ingredientLines.map((originalText) => ({ originalText, optional: false })),
      instructions: instructions.split("\n").map((line) => line.trim()).filter(Boolean),
    });
  }

  if (recipeId && detail.isPending) return <Skeleton label="Loading recipe editor" lines={6} />;
  if (recipeId && detail.isError) return <ErrorRecovery title="Recipe could not be loaded" onRetry={() => void detail.refetch()} />;

  return (
    <main className="page-shell">
      <PageHeader eyebrow={recipeId ? "Edit recipe" : "New recipe"} title={recipeId ? `Make ${detail.data?.title ?? "this recipe"} your own` : "What are we cooking?"} description={recipeId ? "Change the food, servings, or method. Cookfully will refresh the nutrition after you save." : "Start with the recipe as you know it. Cookfully can work out the nutrition after you save."} actions={<Link className="text-link" to={recipeId ? `/app/recipes/${recipeId}` : "/app/recipes"}>Cancel</Link>} />
      <form className="recipe-form recipe-editor" onSubmit={submit} noValidate>
        <section className="recipe-editor__identity" aria-label="Recipe name and yield">
          <Field label="Recipe title" error={errors.title}><input className="input recipe-title-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Lemon chicken with herbs" autoFocus={!recipeId} /></Field>
          <div className="recipe-makes"><span>Makes</span><Field label="Yield quantity" error={errors.yieldQuantity}><DecimalInput aria-label="Yield quantity" value={yieldQuantity} onValueChange={setYieldQuantity} onInput={(event) => setYieldQuantity(event.currentTarget.value)} /></Field><Field label="Yield unit"><input className="input" value={yieldUnit} onChange={(event) => setYieldUnit(event.target.value)} /></Field></div>
        </section>

        <div className="recipe-editor__workbench">
          <section className="recipe-editor__section"><div className="recipe-editor__section-heading"><span>01</span><div><h2>Ingredients</h2><p>One ingredient per line, exactly as you would write it.</p></div></div>
            <Field label="Ingredients, one per line" error={errors.ingredients} hint="Amounts and preparation notes can stay in the same line."><textarea aria-label="Ingredients, one per line" className="input textarea recipe-editor__textarea" value={ingredients} onChange={(event) => setIngredients(event.target.value)} placeholder={"2 chicken breasts\n1 lemon, juiced\n2 tbsp olive oil\nA handful of parsley"} /></Field>
            {detail.data?.ingredients.length ? <details className="structured-review"><summary>Ingredient parsing details</summary><ul>{detail.data.ingredients.map((item) => <li key={item.id}><strong>{item.originalText}</strong><span>{[item.quantityMin, item.quantityMax ? `–${item.quantityMax}` : null, item.unit, item.food, item.preparation].filter(Boolean).join(" ") || "Not parsed"} · {item.parseStatus}{item.matchStatus ? ` / ${item.matchStatus}` : ""}</span></li>)}</ul></details> : null}
          </section>
          <section className="recipe-editor__section"><div className="recipe-editor__section-heading"><span>02</span><div><h2>Method</h2><p>Write each cooking step on its own line.</p></div></div>
            <Field label="Instructions, one step per line"><textarea className="input textarea recipe-editor__textarea" value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder={"Season the chicken generously.\nSear until golden on both sides.\nAdd lemon juice and finish in the oven."} /></Field>
          </section>
        </div>

        <details className="recipe-editor__extras" open={extrasOpen} onToggle={(event) => setExtrasOpen(event.currentTarget.open)}><summary><span><strong>Add a description or source</strong><small>Optional context for remembering where this recipe came from</small></span></summary><div className="recipe-editor__extras-content"><Field label="Description"><textarea className="input textarea" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="A quick weeknight dinner with bright lemon and herbs." /></Field><Field label="Source URL" error={errors.sourceUrl}><input className="input" type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://…" /></Field></div></details>
        {save.error instanceof Error ? <p className="error-text" role="alert">{save.error.message}</p> : null}
        <div className="recipe-editor__save"><p><strong>{recipeId ? "Ready to update it?" : "That’s enough to get started."}</strong><span>Nutrition is estimated after saving and can always be reviewed.</span></p><Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save recipe"}</Button></div>
      </form>
    </main>
  );
}
