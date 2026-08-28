import * as Dialog from "@radix-ui/react-dialog";
import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Field } from "../../components";
import { ApiProblem, recipesApi } from "./api";
import { ThumbnailCropEditor } from "./ThumbnailCropEditor";
import type { ImportConfirmComponent, ImportPreview, ImportRecipePreview, ThumbnailCropWrite } from "./types";

type Step = "url" | "preview" | "confirm";

interface EditableIngredient {
  originalText: string;
  quantityOverride?: string;
}
interface EditableComponent {
  title: string;
  ingredients: EditableIngredient[];
  instructions: string[];
}
const defaultThumbnailCrop = (): ThumbnailCropWrite => ({ x: "0", y: "0", width: "1", height: "1" });

function componentsPayload(components: EditableComponent[]): ImportConfirmComponent[] {
  return components.map((component) => ({
    title: component.title || undefined,
    ingredients: component.ingredients.map((ingredient) => ({
      originalText: ingredient.originalText,
      quantityOverride: ingredient.quantityOverride ?? undefined,
      optional: false,
      remove: false,
    })),
    instructions: component.instructions.map((text) => ({ text, remove: false })),
  }));
}

function editableComponents(preview: ImportRecipePreview): EditableComponent[] {
  return preview.sections.map((section) => ({
    title: section.title ?? "",
    ingredients: section.ingredients.map((ingredient) => ({ originalText: ingredient.originalText })),
    instructions: [...section.instructions],
  }));
}

export function RecipeImportDialog({
  trigger,
  onImported,
  open: controlledOpen,
  onOpenChange,
}: {
  trigger?: React.ReactNode;
  onImported?: () => void | Promise<unknown>;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = (next: boolean) => {
    if (controlledOpen === undefined) setInternalOpen(next);
    onOpenChange?.(next);
  };
  const [step, setStep] = useState<Step>("url");
  const [url, setUrl] = useState("");
  const [validation, setValidation] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [title, setTitle] = useState("");
  const [imageSource, setImageSource] = useState<string | null>(null);
  const [thumbnailCrop, setThumbnailCrop] = useState<ThumbnailCropWrite>(defaultThumbnailCrop);
  const [components, setComponents] = useState<EditableComponent[]>([]);
  const [cookbookRecipes, setCookbookRecipes] = useState<ImportRecipePreview[]>([]);

  const previewMutation = useMutation({
    mutationFn: recipesApi.preview,
    onSuccess: (result) => {
      setPreview(result);
      setCookbookRecipes(result.recipes?.length ? result.recipes : [result]);
      setTitle(result.title);
      setImageSource(result.imageSources[0] ?? null);
      setThumbnailCrop(defaultThumbnailCrop());
      setComponents(editableComponents(result));
      setStep("preview");
    },
    onError: async (error) => {
      // Preview is best-effort. When the synchronous parse can't complete (timeout
      // or an unsupported source), fall back to the legacy background import.
      const fallback = error instanceof ApiProblem && error.status === 503;
      try {
        await onImported?.();
      } catch {
        // The recipe already exists; optional onboarding persistence must not turn
        // that into a failure.
      }
      if (fallback) {
        try {
          const accepted = await recipesApi.import(url);
          setOpen(false);
          if (accepted.resourceId) navigate(`/app/recipes/${accepted.resourceId}`, { state: { jobId: accepted.jobId, recipeSaved: true, importUrl: url, coverStatus: accepted.coverStatus } });
        } catch {
          setValidation("That page could not be imported. Check the address and try again.");
          setStep("url");
        }
        return;
      }
      setValidation("That page could not be read for a preview. Try the address again.");
      setStep("url");
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (write: { parseId: string; title: string; imageSource?: string; imageSourceKind?: "url" | "pdf_thumbnail"; thumbnailCrop?: ThumbnailCropWrite; components: EditableComponent[] }) =>
      recipesApi.confirmImport({
        parseId: write.parseId,
        title: write.title,
        imageSource: write.imageSource ?? undefined,
        imageSourceKind: write.imageSourceKind ?? undefined,
        thumbnailCrop: write.thumbnailCrop,
        components: componentsPayload(write.components),
      }),
    onSuccess: async (accepted) => {
      try {
        await onImported?.();
      } catch {
        // The recipe already exists; optional onboarding persistence must not turn that into a failure.
      } finally {
        setOpen(false);
        if (accepted.resourceId) navigate(`/app/recipes/${accepted.resourceId}`, { state: { jobId: accepted.jobId, recipeSaved: true, importUrl: url, coverStatus: accepted.coverStatus } });
      }
    },
  });

  const mergeMutation = useMutation({
    mutationFn: (target: { recipeId: string; expectedVersion: number }) =>
      recipesApi.mergeImport({
        recipeId: target.recipeId,
        parseId: preview?.parseId ?? "",
        expectedVersion: target.expectedVersion,
        title,
        yieldQuantity: null,
        components: componentsPayload(components),
      }),
    onSuccess: async (accepted) => {
      try {
        await onImported?.();
      } catch {
        // The recipe already exists; optional onboarding persistence must not turn that into a failure.
      } finally {
        setOpen(false);
        if (accepted.resourceId) navigate(`/app/recipes/${accepted.resourceId}`, { state: { jobId: accepted.jobId, recipeSaved: true, importUrl: url } });
      }
    },
  });

  const cookbookConfirmMutation = useMutation({
    mutationFn: async (entries: ImportRecipePreview[]) => {
      const accepted = [];
      for (const entry of entries) {
        accepted.push(await recipesApi.confirmImport({
          parseId: entry.parseId,
          title: entry.title,
          imageSource: entry.imageSources[0],
          imageSourceKind: entry.imageSources[0]?.startsWith("data:image/") ? "pdf_thumbnail" : entry.imageSources[0] ? "url" : undefined,
          thumbnailCrop: defaultThumbnailCrop(),
          components: componentsPayload(editableComponents(entry)),
        }));
      }
      return accepted;
    },
    onSuccess: async () => {
      try {
        await onImported?.();
      } catch {
        // The recipes already exist; onboarding persistence is optional.
      } finally {
        setOpen(false);
        navigate("/app/recipes");
      }
    },
  });

  function submitUrl(event: FormEvent) {
    event.preventDefault();
    try {
      const parsed = new URL(url);
      if (!new Set(["http:", "https:"]).has(parsed.protocol)) throw new Error();
      setValidation("");
      previewMutation.mutate(url);
    } catch {
      setValidation("Enter a complete http or https recipe URL.");
    }
  }

  function confirm() {
    if (!preview) return;
    confirmMutation.mutate({
      parseId: preview.parseId,
      title,
      imageSource: imageSource ?? undefined,
      imageSourceKind: imageSource ? (imageSource.startsWith("data:image/") ? "pdf_thumbnail" : "url") : undefined,
      thumbnailCrop,
      components,
    });
  }

  function updateComponent(index: number, patch: Partial<EditableComponent>) {
    setComponents((current) => current.map((component, i) => (i === index ? { ...component, ...patch } : component)));
  }

  function updateIngredient(componentIndex: number, ingredientIndex: number, patch: Partial<EditableIngredient>) {
    setComponents((current) =>
      current.map((component, i) =>
        i === componentIndex
          ? {
              ...component,
              ingredients: component.ingredients.map((ingredient, j) => (j === ingredientIndex ? { ...ingredient, ...patch } : ingredient)),
            }
          : component,
      ),
    );
  }

  function updateInstruction(componentIndex: number, instructionIndex: number, text: string) {
    setComponents((current) =>
      current.map((component, i) =>
        i === componentIndex
          ? { ...component, instructions: component.instructions.map((value, j) => (j === instructionIndex ? text : value)) }
          : component,
      ),
    );
  }

  function removeComponent(componentIndex: number) {
    setComponents((current) => current.filter((_, i) => i !== componentIndex));
  }

  const busy = previewMutation.isPending || confirmMutation.isPending || mergeMutation.isPending || cookbookConfirmMutation.isPending;
  const cookbookAddable = cookbookRecipes.filter((entry) => entry.duplicates.length === 0);
  const cookbookSkipped = cookbookRecipes.length - cookbookAddable.length;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setStep("url");
          setPreview(null);
          setCookbookRecipes([]);
          setValidation("");
        }
      }}
    >
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog import-wizard" aria-describedby="import-description">
          {step === "url" ? (
            <>
              <Dialog.Title>Import recipes</Dialog.Title>
              <Dialog.Description id="import-description">Paste a public recipe page or a structured cookbook PDF. You can review and edit what we find before it is saved.</Dialog.Description>
              <form className="stack" onSubmit={submitUrl}>
                <Field label="Recipe or cookbook URL" error={validation || (previewMutation.error instanceof Error ? previewMutation.error.message : undefined)}>
                  <input className="input" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/recipe-or-cookbook.pdf" required />
                </Field>
                <div className="actions">
                  <Dialog.Close asChild>
                    <Button type="button" variant="secondary">Cancel</Button>
                  </Dialog.Close>
                  <Button type="submit" disabled={busy}>{previewMutation.isPending ? "Reading page…" : "Start import"}</Button>
                </div>
              </form>
            </>
          ) : step === "preview" && preview ? (
            <>
              <Dialog.Title>Review the recipe</Dialog.Title>
              <Dialog.Description id="import-description">Make any changes before adding it to your collection. Nutrition is calculated after saving.</Dialog.Description>

              {cookbookRecipes.length > 1 ? (
                <section className="import-wizard__cookbook" aria-labelledby="cookbook-import-title">
                  <h3 id="cookbook-import-title">Cookbook found</h3>
                  <p>
                    {cookbookAddable.length > 0
                      ? `${cookbookAddable.length} new recipes are ready to add.`
                      : "Every recipe in this cookbook is already in your collection."}{" "}
                    {cookbookSkipped > 0 ? `${cookbookSkipped} existing match${cookbookSkipped === 1 ? "" : "es"} will be skipped.` : null}
                  </p>
                  <ol>
                    {cookbookRecipes.map((entry) => <li key={entry.parseId}>{entry.title}</li>)}
                  </ol>
                  <Button type="button" onClick={() => cookbookConfirmMutation.mutate(cookbookAddable)} disabled={busy || cookbookAddable.length === 0}>
                    {cookbookConfirmMutation.isPending ? `Adding ${cookbookAddable.length} recipes…` : cookbookAddable.length > 0 ? `Add all ${cookbookAddable.length} new recipes` : "All recipes already added"}
                  </Button>
                  {cookbookConfirmMutation.error instanceof Error ? <p className="error-text" role="alert">{cookbookConfirmMutation.error.message} The import stopped at the failed recipe; try again to continue.</p> : null}
                </section>
              ) : null}

              {preview.duplicates.length > 0 ? (
                <section className="import-wizard__duplicate" role="alert">
                  <strong>It looks like you already have “{preview.duplicates[0].title}”.</strong>
                  <p>You can merge this import into an existing recipe, keep it as a new recipe, or discard it.</p>
                  {preview.duplicates.map((duplicate) => (
                    <div className="import-wizard__duplicate-merge" key={duplicate.id}>
                      <span className="import-wizard__duplicate-title">{duplicate.title}</span>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={mergeMutation.isPending && mergeMutation.variables?.recipeId === duplicate.id}
                        onClick={() => mergeMutation.mutate({ recipeId: duplicate.id, expectedVersion: duplicate.version })}
                      >
                        Merge into existing
                      </Button>
                    </div>
                  ))}
                  <div className="actions">
                    <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Discard</Button>
                    <Button type="button" variant="secondary" onClick={() => { setOpen(false); navigate(`/app/recipes/${preview.duplicates[0].id}`); }}>
                      Open existing
                    </Button>
                    <Button type="button" onClick={() => setStep("confirm")}>Keep this import</Button>
                  </div>
                </section>
              ) : null}

              <form className="stack" onSubmit={(event) => { event.preventDefault(); setStep("confirm"); }}>
                <Field label="Title">
                  <input className="input" value={title} onChange={(event) => setTitle(event.target.value)} />
                </Field>

                {preview.imageSources.length > 0 ? (
                  <fieldset className="import-wizard__images">
                    <legend>Thumbnail</legend>
                    <div className="import-wizard__image-grid">
                      {preview.imageSources.map((source, index) => (
                        <label key={source} className={imageSource === source ? "import-wizard__image is-selected" : "import-wizard__image"}>
                          <input type="radio" name="thumbnail" checked={imageSource === source} onChange={() => setImageSource(source)} aria-label={`Thumbnail ${index + 1}`} />
                          <img src={source} alt="" loading="lazy" />
                        </label>
                      ))}
                    </div>
                    {imageSource ? <ThumbnailCropEditor imageUrl={imageSource} value={thumbnailCrop} onChange={setThumbnailCrop} /> : null}
                  </fieldset>
                ) : null}

                <div className="import-wizard__components">
                  {components.map((component, componentIndex) => (
                    <article className="import-wizard__component" key={componentIndex}>
                      <div className="import-wizard__component-head">
                        <Field label={`Component ${componentIndex + 1} title`}>
                          <input className="input" value={component.title} onChange={(event) => updateComponent(componentIndex, { title: event.target.value })} placeholder="e.g. The chicken" />
                        </Field>
                        {components.length > 1 ? (
                          <Button type="button" variant="ghost" onClick={() => removeComponent(componentIndex)}>Remove</Button>
                        ) : null}
                      </div>

                      <div className="import-wizard__block">
                        <h3>Ingredients</h3>
                        {component.ingredients.map((ingredient, ingredientIndex) => {
                          const needs = preview.sections[componentIndex]?.ingredients[ingredientIndex]?.needsQuantity;
                          return (
                            <div className="import-wizard__ingredient" key={ingredientIndex}>
                              <input
                                className="input"
                                aria-label={`Ingredient ${ingredientIndex + 1} for component ${componentIndex + 1}`}
                                value={ingredient.originalText}
                                onChange={(event) => updateIngredient(componentIndex, ingredientIndex, { originalText: event.target.value })}
                              />
                              {needs ? (
                                <Field label="Quantity" hint="This line has no amount. Add one or leave as written.">
                                  <input className="input" placeholder="e.g. 2 cups" onChange={(event) => updateIngredient(componentIndex, ingredientIndex, { quantityOverride: event.target.value })} />
                                </Field>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>

                      <div className="import-wizard__block">
                        <h3>Method</h3>
                        {component.instructions.map((instruction, instructionIndex) => (
                          <textarea
                            key={instructionIndex}
                            className="input textarea import-wizard__method"
                            aria-label={`Step ${instructionIndex + 1} for component ${componentIndex + 1}`}
                            value={instruction}
                            onChange={(event) => updateInstruction(componentIndex, instructionIndex, event.target.value)}
                          />
                        ))}
                      </div>
                    </article>
                  ))}
                </div>

                <div className="actions">
                  <Button type="button" variant="secondary" onClick={() => setStep("url")}>Back</Button>
                  <Button type="submit">Continue</Button>
                </div>
              </form>
            </>
          ) : preview ? (
            <>
              <Dialog.Title>Add this recipe</Dialog.Title>
              <Dialog.Description id="import-description">Add “{title}” to your collection. Nutrition is calculated in the background.</Dialog.Description>
              {imageSource?.startsWith("data:image/") ? (
                <p className="import-wizard__cover-note" role="status">
                  The cover photo will be attached to this recipe after it is saved.
                </p>
              ) : null}
              <form className="stack" onSubmit={(event) => { event.preventDefault(); confirm(); }}>
                <div className="actions">
                  <Button type="button" variant="secondary" onClick={() => setStep("preview")}>Back</Button>
                  <Button type="submit" disabled={busy}>{confirmMutation.isPending ? "Adding…" : "Add to collection"}</Button>
                </div>
              </form>
            </>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
