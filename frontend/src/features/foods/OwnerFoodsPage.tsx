import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Barcode, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Button, ConfirmDialog, EmptyState, ErrorRecovery, Field, PageHeader } from "../../components";
import { foodsApi } from "./api";
import { CreateFoodDialog } from "./CreateFoodDialog";
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
    },
  });

  if (list.isLoading) {
    return (
      <div className="page-shell owner-foods-page">
        <PageHeader eyebrow="Your nutrition references" title="Foods you know best" description="Loading the foods you’ve saved from labels." />
        <div className="owner-foods-loading" role="status" aria-label="Loading your foods">
          <span /><span /><span />
        </div>
      </div>
    );
  }
  if (list.isError) return <ErrorRecovery title="Could not load your foods." onRetry={() => list.refetch()} />;

  const foods = list.data ?? [];

  return (
    <div className="page-shell owner-foods-page">
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
          <div className="owner-foods-library__heading">
            <div>
              <p className="eyebrow">From your labels</p>
              <h2 id="saved-foods-heading">Saved foods</h2>
            </div>
            <span className="owner-foods-count">{foods.length} {foods.length === 1 ? "food" : "foods"}</span>
          </div>

          <div className="owner-foods-search">
            <Search aria-hidden="true" />
            <Field label="Search saved foods">
              <input
                className="input"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Whey protein, oat milk…"
              />
            </Field>
          </div>

          {foods.length === 0 ? (
            <EmptyState
              title={search ? "No matching foods" : "Save your first label"}
              description={
                search
                  ? `Nothing matches “${search}”. Try a product or brand name.`
                  : "Packaged staples are a good place to start—protein powder, yogurt, bread, sauces, or anything whose label you want Cookfully to remember."
              }
              action={search ? <Button className="button--secondary" onClick={() => setSearch("")}>Clear search</Button> : undefined}
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

        <aside className="owner-foods-guide" aria-labelledby="food-guide-heading">
          <div className="owner-foods-guide__mark" aria-hidden="true"><Sparkles /></div>
          <p className="eyebrow">A little more accurate</p>
          <h2 id="food-guide-heading">Why save a food?</h2>
          <p>Use the label you have in your kitchen when a generic nutrition reference is not specific enough.</p>
          <ol>
            <li><Barcode aria-hidden="true" /><span><strong>Copy the label once</strong><small>Keep calories and macros with the product name.</small></span></li>
            <li><ShieldCheck aria-hidden="true" /><span><strong>Keep the source clear</strong><small>Cookfully can distinguish your label from an estimate.</small></span></li>
          </ol>
          <p className="owner-foods-guide__note">Best for foods you buy repeatedly. Fresh ingredients can continue using Cookfully’s reference library.</p>
        </aside>
      </div>
    </div>
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
        trigger={<Button className="button--text owner-food-row__remove">Remove</Button>}
        title={`Remove ${food.displayName}?`}
        description="Future recipes that reference this food will need to be re-matched."
        confirmLabel="Remove"
        onConfirm={onDeleted}
      />
    </div>
  );
}
