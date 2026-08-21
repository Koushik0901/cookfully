import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type Dispatch, type FormEvent, type SetStateAction, useContext, useEffect, useMemo, useState } from "react";
import { Link, UNSAFE_DataRouterContext, useBlocker, useLocation, useNavigate, useParams } from "react-router-dom";

import { Button, ConfirmDialog, DecimalInput, ErrorRecovery, Field, PageHeader, PageState, Skeleton } from "../../components";
import { Undo2 } from "lucide-react";
import { recipesApi } from "./api";
import { formatCookingInput } from "./formatCooking";
import { FoodPicker } from "../foods/FoodPicker";
import { RecipeDraftPreview } from "./RecipeDraftPreview";
import { ThumbnailCropEditor } from "./ThumbnailCropEditor";
import type { RecipeWrite, ThumbnailCropWrite } from "./types";
import {
  type EditorBlock,
  editorBlocksFromRecipe,
  newEditorBlock,
  previewBlocks,
  serializeRecipeBlocks,
} from "./recipeEditorModel";
import { StructuredIngredientEditor, StructuredMethodEditor } from "./StructuredRecipeFields";

const decimalPattern = /^(?!0(?:\.0{1,3})?$)(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?$/;
const optionalDecimalPattern = /^(?:|0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$/;
const optionalMinutesPattern = /^(?:|0|[1-9][0-9]*)$/;
const NUTRITION_FIELDS = [
  ["calories_kcal", "Calories", "kcal", "caloriesKcal"],
  ["protein_g", "Protein", "g", "proteinG"],
  ["carbohydrate_g", "Carbohydrate", "g", "carbohydrateG"],
  ["fat_g", "Fat", "g", "fatG"],
  ["dietary_fiber_g", "Dietary fiber", "g", "dietaryFiberG"],
  ["sodium_mg", "Sodium", "mg", "sodiumMg"],
  ["potassium_mg", "Potassium", "mg", "potassiumMg"],
  ["calcium_mg", "Calcium", "mg", "calciumMg"],
  ["iron_mg", "Iron", "mg", "ironMg"],
  ["magnesium_mg", "Magnesium", "mg", "magnesiumMg"],
  ["vitamin_c_mg", "Vitamin C", "mg", "vitaminCMg"],
  ["vitamin_d_ug", "Vitamin D", "µg", "vitaminDUg"],
  ["vitamin_b12_ug", "Vitamin B12", "µg", "vitaminB12Ug"],
] as const;
type NutritionField = typeof NUTRITION_FIELDS[number][0];
type NutritionValues = Record<NutritionField, string>;
const emptyNutrition = () => Object.fromEntries(NUTRITION_FIELDS.map(([field]) => [field, ""])) as NutritionValues;
const defaultThumbnailCrop = (): ThumbnailCropWrite => ({ focalX: "0.5", focalY: "0.5", zoom: "1" });

function DataRouterNavigationBlocker({ dirty }: { dirty: boolean }) {
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Leave without saving your recipe changes?")) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  return null;
}

function OptionalNavigationBlocker({ dirty }: { dirty: boolean }) {
  const dataRouter = useContext(UNSAFE_DataRouterContext);
  return dataRouter ? <DataRouterNavigationBlocker dirty={dirty} /> : null;
}

export function RecipeEditorPage() {
  const { recipeId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["recipe", recipeId], queryFn: () => recipesApi.get(recipeId!), enabled: Boolean(recipeId), retry: 1 });
const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [yieldQuantity, setYieldQuantity] = useState("1");
  const [yieldUnit, setYieldUnit] = useState("servings");
  const [prepMinutes, setPrepMinutes] = useState("");
  const [cookMinutes, setCookMinutes] = useState("");
  const [blocks, setBlocks] = useState<EditorBlock[]>(() => [newEditorBlock()]);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [matchesOpen, setMatchesOpen] = useState(location.hash === "#ingredient-matches");
  const [nutritionOpen, setNutritionOpen] = useState(location.hash === "#nutrition");
  const [mobileStep, setMobileStep] = useState<"basics" | "ingredients" | "method" | "nutrition">(location.hash === "#nutrition" ? "nutrition" : "basics");
  const [view, setView] = useState<"edit" | "preview">("edit");
  const [photo, setPhoto] = useState<File | null>(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [photoError, setPhotoError] = useState("");
  const [thumbnailCrop, setThumbnailCrop] = useState<ThumbnailCropWrite>(defaultThumbnailCrop);
  const [showSourceImages, setShowSourceImages] = useState(false);
  const [nutritionValues, setNutritionValues] = useState<NutritionValues>(emptyNutrition);
  const [initialNutritionValues, setInitialNutritionValues] = useState<NutritionValues>(emptyNutrition);
  const [nutritionReason, setNutritionReason] = useState("");
  const [savedRecipeId, setSavedRecipeId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [pasteUndo, setPasteUndo] = useState<{ previous: EditorBlock[]; message: string } | null>(null);
  const photoPreview = useMemo(() => photo ? URL.createObjectURL(photo) : null, [photo]);
  const sourceImages = useQuery({
    queryKey: ["recipe-source-images", recipeId],
    queryFn: () => recipesApi.sourceImages(recipeId!),
    enabled: Boolean(recipeId && detail.data?.sourceUrl && showSourceImages),
    retry: 1,
  });
  const chooseSourcePhoto = useMutation({
    mutationFn: (url: string) => recipesApi.useSourcePhoto(recipeId!, detail.data!.version, url, thumbnailCrop),
    onSuccess: (value) => {
      queryClient.setQueryData(["recipe", recipeId], value);
      setPhoto(null);
      setRemovePhoto(false);
      setShowSourceImages(false);
    },
  });

  useEffect(() => () => { if (photoPreview) URL.revokeObjectURL(photoPreview); }, [photoPreview]);

  useEffect(() => {
    if (!detail.data) return;
    setTitle(detail.data.title);
    setDescription(detail.data.description ?? "");
    setSourceUrl(detail.data.sourceUrl ?? "");
    setYieldQuantity(formatCookingInput(detail.data.yieldQuantity));
    setYieldUnit(detail.data.yieldUnit);
    setPrepMinutes(detail.data.prepMinutes == null ? "" : String(detail.data.prepMinutes));
    setCookMinutes(detail.data.cookMinutes == null ? "" : String(detail.data.cookMinutes));
    setBlocks(editorBlocksFromRecipe(detail.data));
    setExtrasOpen(Boolean(detail.data.description || detail.data.sourceUrl));
    setRemovePhoto(false);
    setThumbnailCrop(detail.data.thumbnailCrop ?? defaultThumbnailCrop());
    const values = emptyNutrition();
    for (const [field, , , responseKey] of NUTRITION_FIELDS) {
      if (responseKey in (detail.data.nutrition ?? {})) {
        const value = detail.data.nutrition?.[responseKey as "caloriesKcal"];
        values[field] = value ?? "";
      } else {
        const value = detail.data.nutrition?.micronutrients?.[responseKey as "dietaryFiberG"]?.value;
        values[field] = value ?? "";
      }
    }
    setNutritionValues(values);
    setInitialNutritionValues(values);
    setDirty(false);
  }, [detail.data]);

  useEffect(() => {
    function beforeUnload(event: BeforeUnloadEvent) {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return;
    function guardInternalNavigation(event: MouseEvent) {
      const target = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(target instanceof HTMLAnchorElement) || target.target === "_blank" || target.download) return;
      const href = target.getAttribute("href");
      if (!href || !href.startsWith("/app") || href === location.pathname + location.search + location.hash) return;
      if (window.confirm("Leave without saving your recipe changes?")) return;
      event.preventDefault();
      event.stopPropagation();
    }
    document.addEventListener("click", guardInternalNavigation, true);
    return () => document.removeEventListener("click", guardInternalNavigation, true);
  }, [dirty, location.hash, location.pathname, location.search]);

  const save = useMutation({
    mutationFn: (value: RecipeWrite) => recipeId && detail.data ? recipesApi.update(recipeId, detail.data.version, value) : recipesApi.create(value),
    onSuccess: async (saved) => {
      let finalRecipe = saved;
      try {
        if (photo) finalRecipe = await recipesApi.uploadPhoto(saved.id, saved.version, photo, thumbnailCrop);
        else if (recipeId && removePhoto && detail.data?.imageUrl) finalRecipe = await recipesApi.removePhoto(saved.id, saved.version);
        const activeCorrections = new Map(
          detail.data?.nutrition?.corrections
            .filter((item) => item.active && item.ingredientId == null)
            .map((item) => [item.field, item.id]) ?? [],
        );
        const correctionPromises: Promise<unknown>[] = [];
        for (const [field] of NUTRITION_FIELDS) {
          const nextValue = nutritionValues[field].trim();
          if (nextValue === initialNutritionValues[field].trim()) continue;
          if (nextValue) {
            correctionPromises.push(
              recipesApi.correct(saved.id, {
                field,
                decimalValue: nextValue,
                reason: nutritionReason.trim() || "Updated in recipe editor",
                rememberMatch: true,
              }),
            );
          } else {
            const correctionId = activeCorrections.get(field);
            if (correctionId) correctionPromises.push(recipesApi.resetCorrection(saved.id, correctionId));
          }
        }
        const results = await Promise.allSettled(correctionPromises);
        const failures = results.filter((r) => r.status === "rejected");
        if (failures.length) {
          const message = failures[0] instanceof Error ? failures[0].message : "Nutrition corrections failed.";
          throw new Error(message);
        }
      } catch (error) {
        setSavedRecipeId(saved.id);
        setDirty(false);
        setPhotoError(error instanceof Error ? `Recipe saved, but one finishing change failed: ${error.message}` : "Recipe saved, but one finishing change failed.");
        return;
      }
      if ("ingredients" in finalRecipe) queryClient.setQueryData(["recipe", finalRecipe.id], finalRecipe);
      else queryClient.removeQueries({ queryKey: ["recipe", finalRecipe.id], exact: true });
void queryClient.invalidateQueries({ queryKey: ["recipes"] });
      setDirty(false);
      navigate(`/app/recipes/${finalRecipe.id}`, { state: { recipeSaved: true } });
    },
  });

  const setEditorBlocks: Dispatch<SetStateAction<EditorBlock[]>> = (value) => {
    setDirty(true);
    setBlocks(value);
  };

  function rowsSplit(previous: EditorBlock[], count: number, kind: "ingredients" | "steps") {
    setDirty(true);
    setPasteUndo({ previous, message: `${count} ${kind === "ingredients" ? "ingredient rows" : "method steps"} created from your paste.` });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (!title.trim()) nextErrors.title = "Recipe title is required.";
    if (!decimalPattern.test(yieldQuantity)) nextErrors.yieldQuantity = "Use a positive value with up to three decimal places (and no exponent).";
    if (!optionalMinutesPattern.test(prepMinutes) || Number(prepMinutes) > 1440) nextErrors.prepMinutes = "Use a whole number from 0 to 1440 minutes.";
    if (!optionalMinutesPattern.test(cookMinutes) || Number(cookMinutes) > 1440) nextErrors.cookMinutes = "Use a whole number from 0 to 1440 minutes.";
    const titledBlocks = blocks.filter((block) => block.title.trim());
    const sectionTitles = titledBlocks.map((block) => block.title.trim());
    if (new Set(sectionTitles).size !== sectionTitles.length) nextErrors.sections = "Component names must be unique.";
    const hasIngredients = blocks.some((block) => block.ingredients.some((item) => item.originalText.trim()));
    if (!hasIngredients) nextErrors.ingredients = "Enter at least one ingredient.";
    if (sourceUrl) {
      try { new URL(sourceUrl); } catch { nextErrors.sourceUrl = "Enter a complete source URL."; }
    }
    for (const [field, label] of NUTRITION_FIELDS) {
      if (!optionalDecimalPattern.test(nutritionValues[field].trim())) {
        nextErrors[`nutrition-${field}`] = `${label} must be a non-negative decimal with up to six decimal places.`;
      }
    }
    setErrors(nextErrors);
    setPhotoError("");
    if (Object.keys(nextErrors).length) {
      const hasNutritionError = Object.keys(nextErrors).some((key) => key.startsWith("nutrition-"));
      setMobileStep(nextErrors.title || nextErrors.yieldQuantity || nextErrors.prepMinutes || nextErrors.cookMinutes ? "basics" : nextErrors.ingredients ? "ingredients" : hasNutritionError ? "nutrition" : "method");
      return;
    }
    save.mutate(serializeRecipeBlocks(blocks, { title, description, sourceUrl, yieldQuantity, yieldUnit, prepMinutes, cookMinutes, thumbnailCrop }));
  }

  if (recipeId && detail.isPending) return <PageState><Skeleton label="Loading recipe editor" lines={6} /></PageState>;
  if (recipeId && detail.isError) return <PageState><ErrorRecovery title="Recipe could not be loaded" onRetry={() => void detail.refetch()} /></PageState>;

  return (
    <>
      <OptionalNavigationBlocker dirty={dirty} />
      <main className="page-shell recipe-editor-page">
      <PageHeader eyebrow={recipeId ? "Edit recipe" : "New recipe"} title={recipeId ? `Make ${detail.data?.title ?? "this recipe"} your own` : "What are we cooking?"} description={recipeId ? "Change the food, servings, or method. Cookfully will refresh the nutrition after you save." : "Start with the recipe as you know it. Cookfully can work out the nutrition after you save."} actions={<Link className="text-link" to={recipeId ? `/app/recipes/${recipeId}` : "/app/recipes"}>Cancel</Link>} />
      <nav className="recipe-editor__view-toggle" aria-label="Recipe editor views">
        <button type="button" aria-pressed={view === "edit"} onClick={() => setView("edit")}>Edit</button>
        <button type="button" aria-pressed={view === "preview"} onClick={() => setView("preview")}>Preview</button>
      </nav>
      <RecipeDraftPreview
        title={title}
        description={description}
        sourceUrl={sourceUrl}
        yieldQuantity={yieldQuantity}
         yieldUnit={yieldUnit}
         photoUrl={photoPreview ?? (removePhoto ? null : detail.data?.imageUrl ?? null)}
         thumbnailCrop={thumbnailCrop}
         blocks={previewBlocks(blocks)}
        macros={NUTRITION_FIELDS.slice(0, 4).filter(([field]) => nutritionValues[field].trim()).map(([field, label, unit]) => ({ label: `${label} (${unit})`, value: nutritionValues[field].trim() }))}
        className={view === "preview" ? undefined : "u-hidden"}
      />
      <form className={`recipe-form recipe-editor recipe-editor--step-${mobileStep}${view === "edit" ? "" : " u-hidden"}`} onSubmit={submit} onChange={() => setDirty(true)} noValidate>
        <section className="recipe-editor__identity" aria-label="Recipe name and yield">
          <Field label="Recipe title" error={errors.title}><input className="input recipe-title-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Lemon chicken with herbs" autoFocus={!recipeId} /></Field>
          <div className="recipe-editor__identity-details"><div className="recipe-makes"><span>Makes</span><Field label="Yield quantity" error={errors.yieldQuantity}><DecimalInput aria-label="Yield quantity" value={yieldQuantity} onValueChange={setYieldQuantity} onInput={(event) => setYieldQuantity(event.currentTarget.value)} /></Field><Field label="Yield unit"><input className="input" value={yieldUnit} onChange={(event) => setYieldUnit(event.target.value)} /></Field></div><div className="recipe-times"><Field label="Prep minutes" hint="Optional" error={errors.prepMinutes}><input className="input" inputMode="numeric" pattern="[0-9]*" value={prepMinutes} onChange={(event) => setPrepMinutes(event.currentTarget.value)} /></Field><Field label="Cook minutes" hint="Optional" error={errors.cookMinutes}><input className="input" inputMode="numeric" pattern="[0-9]*" value={cookMinutes} onChange={(event) => setCookMinutes(event.currentTarget.value)} /></Field></div></div>
        </section>

        <nav className="recipe-editor__mobile-steps" aria-label="Recipe editing steps">
          {(["basics", "ingredients", "method", "nutrition"] as const).map((step, index) => <button type="button" key={step} aria-label={step[0].toUpperCase() + step.slice(1)} aria-current={mobileStep === step ? "step" : undefined} onClick={() => { setMobileStep(step); if (step === "nutrition") setNutritionOpen(true); }}><span aria-hidden="true">{index + 1}</span>{step[0].toUpperCase() + step.slice(1)}</button>)}
        </nav>

        {pasteUndo ? <div className="recipe-editor__paste-feedback" role="status"><span>{pasteUndo.message}</span><Button type="button" variant="ghost" size="sm" onClick={() => { setBlocks(pasteUndo.previous); setPasteUndo(null); }}><Undo2 aria-hidden="true" />Undo</Button></div> : null}

        <div className="recipe-editor__workbench">
          <StructuredIngredientEditor blocks={blocks} setBlocks={setEditorBlocks} error={errors.ingredients} onRowsSplit={rowsSplit} />
          <StructuredMethodEditor blocks={blocks} setBlocks={setEditorBlocks} onRowsSplit={rowsSplit} />
        </div>

        {detail.data?.ingredients.some((item) => item.matchStatus === "ambiguous" || item.matchStatus === "unmatched" || item.resolutionKind === "provisional") ? <details className="structured-review" id="ingredient-matches" open={matchesOpen} onToggle={(event) => setMatchesOpen(event.currentTarget.open)}><summary>Improve nutrition matches</summary><p className="muted">The recipe is usable as-is. Choose a reference only where you want a more complete nutrition estimate.</p><ul>{detail.data.ingredients.filter((item) => item.matchStatus === "ambiguous" || item.matchStatus === "unmatched" || item.resolutionKind === "provisional").map((item) => <li key={item.id}><span><strong>{item.originalText}</strong><small>{item.resolutionKind === "provisional" ? `provisional estimate from ${item.candidateEvidence?.length ?? 0} foods` : item.matchStatus}</small></span><FoodPicker recipeId={detail.data.id} ingredientId={item.id} ingredientName={item.food || item.originalText} trigger={<Button type="button" variant="secondary" size="sm">Choose food</Button>} onSelected={() => void detail.refetch()} /></li>)}</ul></details> : null}

        <details className="recipe-editor__extras" open={extrasOpen} onToggle={(event) => setExtrasOpen(event.currentTarget.open)}><summary><span><strong>Add a description or source</strong><small>Optional context for remembering where this recipe came from</small></span></summary><div className="recipe-editor__extras-content"><Field label="Description"><textarea className="input textarea" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="A quick weeknight dinner with bright lemon and herbs." /></Field><Field label="Source URL" error={errors.sourceUrl}><input className="input" type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://…" /></Field></div></details>
        <details className="recipe-editor__nutrition" id="nutrition" open={nutritionOpen} onToggle={(event) => setNutritionOpen(event.currentTarget.open)}>
          <summary><span><strong>Nutrition values</strong><small>Optional manual values for labels or trusted sources</small></span></summary>
          <div className="recipe-editor__nutrition-content">
            <p className="muted">Leave calculated values unchanged to keep using Cookfully’s estimate. Changing a value creates a clearly labeled manual override.</p>
            <div className="recipe-editor__nutrition-grid recipe-editor__nutrition-grid--macros">
              {NUTRITION_FIELDS.slice(0, 4).map(([field, label, unit]) => <Field key={field} label={`${label} (${unit})`} error={errors[`nutrition-${field}`]}><DecimalInput value={nutritionValues[field]} onValueChange={(value) => setNutritionValues((current) => ({ ...current, [field]: value }))} onInput={(event) => { const value = event.currentTarget.value; setNutritionValues((current) => ({ ...current, [field]: value })); }} /></Field>)}
            </div>
            <details className="recipe-editor__micronutrients">
              <summary>Edit micronutrients</summary>
              <div className="recipe-editor__nutrition-grid">
                {NUTRITION_FIELDS.slice(4).map(([field, label, unit]) => <Field key={field} label={`${label} (${unit})`} error={errors[`nutrition-${field}`]}><DecimalInput value={nutritionValues[field]} onValueChange={(value) => setNutritionValues((current) => ({ ...current, [field]: value }))} onInput={(event) => { const value = event.currentTarget.value; setNutritionValues((current) => ({ ...current, [field]: value })); }} /></Field>)}
              </div>
            </details>
            <Field label="Source or reason" hint="For example: package label, cookbook, or clinician-provided value."><input className="input" value={nutritionReason} onChange={(event) => setNutritionReason(event.target.value)} /></Field>
          </div>
        </details>
        {photoPreview || (detail.data?.imageUrl && !removePhoto) ? <section className="recipe-editor__crop" aria-labelledby="recipe-crop-heading"><p className="eyebrow" id="recipe-crop-heading">Frame your cover</p><ThumbnailCropEditor imageUrl={photoPreview ?? detail.data!.imageUrl!} value={thumbnailCrop} onChange={setThumbnailCrop} /></section> : null}
        <section className="recipe-editor__photo" aria-labelledby="recipe-photo-heading"><div><p className="eyebrow">A little recognition</p><h3 id="recipe-photo-heading">Choose the cover</h3><p>Use your own photo, keep the recipe photo-free, or pick one image from the original source.</p></div><div className="recipe-editor__photo-body">{photoPreview ? <img src={photoPreview} alt="Preview of the selected recipe photo" /> : detail.data?.imageUrl && !removePhoto ? <img src={detail.data.imageUrl} alt={`Current photo for ${detail.data.title}`} /> : <div className="recipe-editor__photo-empty">No cover selected.</div>}<div className="recipe-editor__photo-actions"><label className="file-button"><span>{photo || (detail.data?.imageUrl && !removePhoto) ? "Upload replacement" : "Upload photo"}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const selected = event.currentTarget.files?.[0] ?? null; setPhoto(selected); setRemovePhoto(false); setPhotoError(""); }} /></label>{recipeId && detail.data?.sourceUrl ? <Button type="button" variant="secondary" onClick={() => setShowSourceImages((value) => !value)}>{showSourceImages ? "Hide source photos" : "Choose from source"}</Button> : null}{photo || (detail.data?.imageUrl && !removePhoto) ? (detail.data?.imageUrl && !photoPreview ? <ConfirmDialog trigger={<Button type="button" variant="ghost">Remove photo</Button>} title="Remove this recipe photo?" description="The photo will be removed when you save these recipe changes. You can upload a replacement before saving." confirmLabel="Remove photo" onConfirm={() => { setPhoto(null); setRemovePhoto(true); }} /> : <Button type="button" variant="ghost" onClick={() => { setPhoto(null); setRemovePhoto(Boolean(detail.data?.imageUrl)); }}>Remove photo</Button>) : null}</div>{showSourceImages ? <div className="source-image-picker" aria-label="Photos from the original recipe">{sourceImages.isPending ? <p>Finding photos on the source page…</p> : sourceImages.isError ? <p className="error-text">Source photos could not be loaded.</p> : sourceImages.data?.length ? sourceImages.data.map((item, index) => <button type="button" key={item.url} onClick={() => chooseSourcePhoto.mutate(item.url)} disabled={chooseSourcePhoto.isPending}><img src={item.url} alt={`Source photo option ${index + 1}`} /></button>) : <p>No usable source photos were found.</p>}</div> : null}{chooseSourcePhoto.error instanceof Error ? <p className="error-text" role="alert">{chooseSourcePhoto.error.message}</p> : null}</div></section>
        {save.error instanceof Error ? <p className="error-text" role="alert">{save.error.message}</p> : null}
        {photoError ? <p className="error-text" role="alert">{photoError}{savedRecipeId ? <> <Link to={`/app/recipes/${savedRecipeId}`}>Open the saved recipe</Link></> : null}</p> : null}
        <div className="recipe-editor__save"><p><strong>{recipeId ? "Ready to update it?" : "That’s enough to get started."}</strong><span>Nutrition is estimated after saving and can always be reviewed.</span></p><Button type="submit" disabled={save.isPending || Boolean(savedRecipeId)}>{save.isPending ? "Saving…" : "Save recipe"}</Button></div>
      </form>
      </main>
    </>
  );
}
