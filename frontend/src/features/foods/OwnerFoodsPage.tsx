import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Barcode, ChevronDown, CircleHelp, ShieldCheck } from "lucide-react";
import { Button, ConfirmDialog, EmptyState, ErrorRecovery, PageHeader, PageState, SearchField, SectionHeading, Skeleton } from "../../components";
import { foodsApi } from "./api";
import { CreateFoodDialog } from "./CreateFoodDialog";
import { invalidateFoodChoiceQueries } from "./foodChoiceQueries";
import { formatCookingNumber } from "../recipes/formatCooking";
import type { OwnerFood } from "./types";

export function OwnerFoodsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");

  const list = useQuery({
    queryKey: ["owner-foods", search],
    queryFn: () => foodsApi.listUserFoods(search || undefined),
  });

  const deleteFood = useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      foodsApi.deleteUserFood(id, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["owner-foods"] });
      void invalidateFoodChoiceQueries(queryClient);
    },
  });

  if (list.isLoading) {
    return (
      <main className="page-shell owner-foods-page">
        <PageHeader eyebrow="Your nutrition references" title="Foods you know best" description="Loading the foods you’ve saved from labels." />
        <Skeleton label="Loading your foods" lines={5} />
      </main>
    );
  }
  if (list.isError) return <PageState><ErrorRecovery title="Could not load your foods" onRetry={() => list.refetch()} /></PageState>;

  const foods = list.data ?? [];

  return (
    <main className="page-shell owner-foods-page">
      <PageHeader
        eyebrow="Your nutrition references"
        title="Foods you know best"
        description="Save foods from product labels so recipes can use the nutrition information you trust."
        actions={
          <CreateFoodDialog
            ingredientName=""
            trigger={<Button>New food</Button>}
            onCreated={() => queryClient.invalidateQueries({ queryKey: ["owner-foods"] })}
          />
        }
      />

      <div className="owner-foods-layout">
        <section className="owner-foods-library" aria-labelledby="saved-foods-heading">
          <SectionHeading className="owner-foods-library__heading" eyebrow="From your labels" title="Saved foods" id="saved-foods-heading" meta={`${foods.length} ${foods.length === 1 ? "food" : "foods"}`} />

          <SearchField className="owner-foods-search" label="Search saved foods" value={search} onChange={(event) => setSearch(event.target.value)} onClear={() => setSearch("")} placeholder="Oat milk, sourdough bread…" />

          <details className="owner-foods-help">
            <summary>
              <CircleHelp aria-hidden="true" />
              <span><strong>When to save a food</strong><small>Use your own label when a generic reference is not specific enough.</small></span>
              <ChevronDown aria-hidden="true" />
            </summary>
            <div className="owner-foods-help__content">
              <p>Best for packaged foods you buy repeatedly. Fresh ingredients can continue using Cookfully’s reference library.</p>
              <ul>
                <li><Barcode aria-hidden="true" /><span><strong>Copy the label once</strong><small>Keep calories and macros with the product name.</small></span></li>
                <li><ShieldCheck aria-hidden="true" /><span><strong>Keep the source clear</strong><small>Cookfully can distinguish your label from an estimate.</small></span></li>
              </ul>
            </div>
          </details>

          {foods.length === 0 ? (
            <EmptyState
              title={search ? "No matching foods" : "Save your first label"}
              description={
                search
                  ? `Nothing matches “${search}”. Try a product or brand name.`
                  : "Packaged staples are a good place to start—protein powder, yogurt, bread, sauces, or anything whose label you want Cookfully to remember."
              }
              action={search ? <Button variant="secondary" onClick={() => setSearch("")}>Clear search</Button> : undefined}
            />
          ) : (
            <ul className="owner-foods-list">
              {foods.map((food) => (
                <li key={food.id} className="owner-food-card">
                  <OwnerFoodRow
                    food={food}
                    onDeleted={() => deleteFood.mutate({ id: food.id, version: food.version })}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}

function OwnerFoodRow({ food, onDeleted }: { food: OwnerFood; onDeleted: () => void }) {
  const per = Number(food.basisGrams) !== 100 ? `per ${formatCookingNumber(food.basisGrams)}g` : "per 100g";
  const serving = food.typicalServingUnit
    ? `${formatCookingNumber(food.typicalServingG)}g (1 ${food.typicalServingUnit})`
    : null;

  return (
    <div className="owner-food-row">
      <span className="owner-food-row__stamp" aria-hidden="true"><Barcode /></span>
      <div className="owner-food-row__body">
        <div className="owner-food-row__identity">
          <h3 className="owner-food-row__name">{food.displayName}</h3>
          {food.brand && <span className="owner-food-row__brand">{food.brand}</span>}
        </div>
        <span className="owner-food-row__serving">{per}{serving ? ` · ${serving}` : ""}</span>
        <dl className="owner-food-row__nutrition" aria-label={`Nutrition for ${food.displayName}`}>
          <div><dt>Calories</dt><dd>{formatCookingNumber(food.caloriesKcal, 0)} kcal</dd></div>
          <div><dt><i className="nutrient-dot nutrient-dot--protein" aria-hidden="true" />Protein</dt><dd>{formatCookingNumber(food.proteinG, 1)} g</dd></div>
          <div><dt><i className="nutrient-dot nutrient-dot--carbohydrate" aria-hidden="true" />Carbs</dt><dd>{formatCookingNumber(food.carbohydrateG, 1)} g</dd></div>
          <div><dt><i className="nutrient-dot nutrient-dot--fat" aria-hidden="true" />Fat</dt><dd>{formatCookingNumber(food.fatG, 1)} g</dd></div>
        </dl>
      </div>
      <ConfirmDialog
        trigger={<Button variant="ghost" className="owner-food-row__remove">Remove</Button>}
        title={`Remove ${food.displayName}?`}
        description="This removes the food from future matching. Existing recipes keep their saved choice until you change it."
        confirmLabel="Remove"
        onConfirm={onDeleted}
      />
    </div>
  );
}
