import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, ConfirmDialog, EmptyState, ErrorRecovery, Field, PageHeader } from "../../components";
import { foodsApi } from "./api";
import { CreateFoodDialog } from "./CreateFoodDialog";
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

  if (list.isLoading) return <PageHeader eyebrow="My foods" title="Loading\u2026" />;
  if (list.isError) return <ErrorRecovery title="Could not load your foods." onRetry={() => list.refetch()} />;

  const foods = list.data ?? [];

  return (
    <div className="page-shell">
      <PageHeader
        eyebrow="My foods"
        title="Your food library"
        description="Foods you have created from product labels. They take priority over USDA reference matches."
        actions={
          <CreateFoodDialog
            ingredientName=""
            trigger={<Button>New food</Button>}
            onCreated={() => queryClient.invalidateQueries({ queryKey: ["owner-foods"] })}
          />
        }
      />

      <Field label="Search your foods">
        <input
          className="input"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="whey protein, oat milk..."
        />
      </Field>

      {foods.length === 0 && (
        <EmptyState
          title={search ? "No matching foods" : "No foods yet"}
          description={
            search
              ? `Nothing matches "${search}".`
              : "Create your first food from a product label — it will auto-match future recipe imports."
          }
        />
      )}

      {foods.length > 0 && (
        <ul className="owner-foods-list">
          {foods.map((food) => (
            <li key={food.id} className="owner-food-card">
              <OwnerFoodRow
                food={food}
                onDeleted={() =>
                  deleteFood.mutate({ id: food.id, version: food.version })
                }
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OwnerFoodRow({ food, onDeleted }: { food: OwnerFood; onDeleted: () => void }) {
  const macros = [
    `${food.caloriesKcal.toFixed(0)} kcal`,
    `${food.proteinG.toFixed(1)}g P`,
    `${food.carbohydrateG.toFixed(1)}g C`,
    `${food.fatG.toFixed(1)}g F`,
  ].join(" · ");

  const per = food.basisGrams !== 100 ? `per ${food.basisGrams}g` : "per 100g";
  const serving = food.typicalServingUnit
    ? `${food.typicalServingG?.toFixed(0)}g (1 ${food.typicalServingUnit})`
    : null;

  return (
    <div className="owner-food-row">
      <div className="owner-food-row__body">
        <strong className="owner-food-row__name">{food.displayName}</strong>
        {food.brand && <span className="muted owner-food-row__brand"> &mdash; {food.brand}</span>}
        <span className="owner-food-row__macros">{macros}</span>
        <span className="muted">{per}{serving ? ` · ${serving}` : ""}</span>
      </div>
      <ConfirmDialog
        trigger={<Button className="button--text">Remove</Button>}
        title={`Remove ${food.displayName}?`}
        description="Future recipes that reference this food will need to be re-matched."
        confirmLabel="Remove"
        onConfirm={onDeleted}
      />
    </div>
  );
}
