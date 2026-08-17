import type { RecipeCollection } from "./types";

export function RecipeCollectionStrip({
  collections,
  recipesCount,
  unfiledCount,
  selected,
  onSelect,
}: {
  collections: RecipeCollection[];
  recipesCount: number;
  unfiledCount: number;
  selected: string;
  onSelect: (id: string) => void;
}) {
  if (!collections.length && !recipesCount) return null;
  return (
    <nav className="recipe-collection-strip" aria-label="Recipe collections">
      <button type="button" className={selected === "" ? "is-selected" : ""} aria-pressed={selected === ""} onClick={() => onSelect("")}>All <span>{recipesCount}</span></button>
      {collections.map((collection) => <button type="button" key={collection.id} className={selected === collection.id ? "is-selected" : ""} aria-pressed={selected === collection.id} onClick={() => onSelect(collection.id)}>{collection.name} <span>{collection.recipeCount}</span></button>)}
      <button type="button" className={selected === "__unfiled__" ? "is-selected" : ""} aria-pressed={selected === "__unfiled__"} onClick={() => onSelect("__unfiled__")}>Unfiled <span>{unfiledCount}</span></button>
    </nav>
  );
}
