import { ExternalLink } from "lucide-react";

import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingText, servingLabel, sourceHost } from "./formatCooking";

interface DraftBlock {
  title: string;
  ingredients: string;
  instructions: string;
}

interface DraftMacro {
  label: string;
  value: string;
}

export function RecipeDraftPreview({
  title,
  description,
  sourceUrl,
  yieldQuantity,
  yieldUnit,
  photoUrl,
  blocks,
  macros = [],
}: {
  title: string;
  description: string;
  sourceUrl: string;
  yieldQuantity: string;
  yieldUnit: string;
  photoUrl: string | null;
  blocks: DraftBlock[];
  macros?: DraftMacro[];
}) {
  const ingredientCount = blocks.reduce((total, block) => total + block.ingredients.split("\n").filter((line) => line.trim()).length, 0);
  const stepCount = blocks.reduce((total, block) => total + block.instructions.split("\n").filter((line) => line.trim()).length, 0);

  return (
    <div className="recipe-draft-preview" aria-label="Recipe preview">
      <section className="recipe-hero" aria-labelledby="recipe-preview-title">
        <div className="recipe-hero__media">
          {photoUrl ? <img src={photoUrl} alt={title} /> : <RecipeFallbackArt title={title} />}
        </div>
        <div className="recipe-hero__copy">
          <p className="eyebrow">From your kitchen</p>
          <h1 id="recipe-preview-title">{title || "Untitled recipe"}</h1>
          {description ? <p className="lede">{description}</p> : null}
          <div className="recipe-hero__facts">
            <span><strong>{servingLabel(yieldQuantity, yieldUnit)}</strong></span>
            <span><strong>{ingredientCount}</strong> ingredient{ingredientCount === 1 ? "" : "s"}</span>
            <span><strong>{stepCount}</strong> step{stepCount === 1 ? "" : "s"}</span>
            {sourceUrl && sourceHost(sourceUrl) ? <a className="recipe-source" href={sourceUrl} target="_blank" rel="noopener noreferrer">From {sourceHost(sourceUrl)} <ExternalLink aria-hidden="true" /></a> : null}
          </div>
          {macros.length ? (
            <dl className="recipe-draft-preview__macros">
              {macros.map((macro) => (
                <div key={macro.label}><dt>{macro.label}</dt><dd>{macro.value}</dd></div>
              ))}
            </dl>
          ) : (
            <p className="muted">Nutrition is calculated after saving.</p>
          )}
        </div>
      </section>

      <section className="recipe-reading-grid" aria-label="Preview ingredients and method">
        <section className="recipe-reading-panel recipe-reading-panel--ingredients" aria-labelledby="recipe-preview-ingredients-heading">
          <div className="section-heading"><h2 id="recipe-preview-ingredients-heading">Ingredients</h2><span>{ingredientCount} items</span></div>
          {ingredientCount ? (
            <ul className="ingredient-list">
              {blocks.map((block, blockIndex) => {
                const ingredients = block.ingredients.split("\n").filter((line) => line.trim());
                if (!ingredients.length) return null;
                return (
                  <li key={blockIndex} className="ingredient-section" aria-label={`${block.title || `Component ${blockIndex + 1}`} ingredients`}>
                    {block.title.trim() ? <h3>{block.title}</h3> : null}
                    <ul>
                      {ingredients.map((ingredient, ingredientIndex) => (
                        <li key={`${ingredientIndex}-${ingredient}`}><span className="ingredient-text">{formatCookingText(ingredient)}</span></li>
                      ))}
                    </ul>
                  </li>
                );
              })}
            </ul>
          ) : <p className="muted">No ingredients were provided.</p>}
        </section>

        <section className="recipe-reading-panel recipe-reading-panel--method" aria-labelledby="recipe-preview-method-heading">
          <div className="section-heading"><h2 id="recipe-preview-method-heading">Method</h2><span>{stepCount} steps</span></div>
          {stepCount ? (
            <ol className="instruction-list">
              {blocks.map((block, blockIndex) => {
                const steps = block.instructions.split("\n").filter((line) => line.trim());
                if (!steps.length) return null;
                return (
                  <li key={blockIndex} className="instruction-section" aria-label={`${block.title || `Component ${blockIndex + 1}`} instructions`}>
                    {block.title.trim() ? <h3>{block.title}</h3> : null}
                    <ol>
                      {steps.map((step, stepIndex) => <li key={`${stepIndex}-${step}`}>{formatCookingText(step)}</li>)}
                    </ol>
                  </li>
                );
              })}
            </ol>
          ) : <p className="muted">No instructions were provided.</p>}
        </section>
      </section>
    </div>
  );
}