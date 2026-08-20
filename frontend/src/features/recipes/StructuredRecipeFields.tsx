import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { type ClipboardEvent, type Dispatch, type SetStateAction } from "react";

import { Button, Field } from "../../components";
import { Checkbox } from "../../components/ui/checkbox";
import {
  type EditorBlock,
  newEditorBlock,
  newIngredient,
  newMethodStep,
  moveAt,
  splitPastedRows,
} from "./recipeEditorModel";

type SetBlocks = Dispatch<SetStateAction<EditorBlock[]>>;

function blockName(block: EditorBlock, index: number) {
  return block.title.trim() || (index === 0 ? "main recipe" : `component ${index + 1}`);
}

function ReorderActions({ label, index, length, onMove, onRemove }: { label: string; index: number; length: number; onMove: (to: number) => void; onRemove: () => void }) {
  return (
    <div className="structured-row__actions">
      <button type="button" aria-label={`Move ${label} up`} disabled={index === 0} onClick={() => onMove(index - 1)}><ArrowUp aria-hidden="true" /></button>
      <button type="button" aria-label={`Move ${label} down`} disabled={index === length - 1} onClick={() => onMove(index + 1)}><ArrowDown aria-hidden="true" /></button>
      <button type="button" aria-label={`Remove ${label}`} onClick={onRemove}><Trash2 aria-hidden="true" /></button>
    </div>
  );
}

export function StructuredIngredientEditor({
  blocks,
  setBlocks,
  error,
  onRowsSplit,
}: {
  blocks: EditorBlock[];
  setBlocks: SetBlocks;
  error?: string;
  onRowsSplit: (previous: EditorBlock[], count: number, kind: "ingredients" | "steps") => void;
}) {
  function updateBlock(blockKey: string, patch: Partial<Pick<EditorBlock, "title" | "ingredients">>) {
    setBlocks((current) => current.map((block) => block.key === blockKey ? { ...block, ...patch } : block));
  }

  function pasteLines(event: ClipboardEvent<HTMLInputElement>, block: EditorBlock, rowIndex: number) {
    if (block.ingredients[rowIndex]?.originalText.trim()) return;
    const lines = splitPastedRows(event.clipboardData.getData("text"));
    if (lines.length < 2) return;
    event.preventDefault();
    const previous = blocks;
    const replacement = lines.map((originalText) => newIngredient({ originalText }));
    const ingredients = [...block.ingredients.slice(0, rowIndex), ...replacement, ...block.ingredients.slice(rowIndex + 1)];
    updateBlock(block.key, { ingredients });
    onRowsSplit(previous, replacement.length, "ingredients");
  }

  return (
    <section className="structured-workbench recipe-editor__ingredients-workbench" aria-labelledby="structured-ingredients-heading">
      <header className="structured-workbench__heading">
        <div><p className="eyebrow">Ingredients</p><h2 id="structured-ingredients-heading">Build a list you can scan</h2><p>One ingredient per row. Paste a multiline list into an empty row and Cookfully will split it for you.</p></div>
        <span>{blocks.reduce((total, block) => total + block.ingredients.filter((item) => item.originalText.trim()).length, 0)} ingredients</span>
      </header>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <div className="structured-components">
        {blocks.map((block, blockIndex) => (
          <section className="structured-component" key={block.key} aria-label={`${blockName(block, blockIndex)} ingredients`}>
            <header className="structured-component__heading">
              {blockIndex === 0 && !block.title.trim() ? <div><strong>Main recipe</strong><small>Everything that belongs to the dish as a whole</small></div> : (
                <Field label="Component name" hint="For example: chicken, rice, or sauce">
                  <input className="input" value={block.title} onChange={(event) => updateBlock(block.key, { title: event.target.value })} placeholder="For the sauce" aria-label={`Component ${blockIndex + 1} name`} />
                </Field>
              )}
              {blockIndex > 0 ? <button type="button" className="structured-component__remove" onClick={() => setBlocks((current) => current.filter((item) => item.key !== block.key))}>Remove component</button> : null}
            </header>
            <div className="ingredient-rows">
              {block.ingredients.map((row, rowIndex) => {
                const label = `ingredient ${rowIndex + 1} for ${blockName(block, blockIndex)}`;
                const parsed = Boolean(row.quantityMin || row.quantityMax || row.unit || row.food || row.preparation);
                return (
                  <article className="ingredient-row" key={row.key}>
                    <span className="structured-row__number" aria-hidden="true">{String(rowIndex + 1).padStart(2, "0")}</span>
                    <div className="ingredient-row__body">
                      <label className="ingredient-row__primary">
                        <span className="visually-hidden">{label}</span>
                        <input
                          className="input"
                          value={row.originalText}
                          onChange={(event) => {
                            const ingredients = block.ingredients.map((item) => item.key === row.key ? { ...item, originalText: event.target.value } : item);
                            updateBlock(block.key, { ingredients });
                          }}
                          onPaste={(event) => pasteLines(event, block, rowIndex)}
                          placeholder={rowIndex === 0 ? "2 chicken breasts, thinly sliced" : "Add another ingredient"}
                        />
                      </label>
                      <details className="ingredient-row__details">
                        <summary><span>{parsed ? "Parsed details" : "Add amount details"}</span>{parsed ? <small>Structured</small> : null}</summary>
                        <div className="ingredient-row__detail-grid">
                          <Field label="Amount"><input className="input" inputMode="decimal" value={row.quantityMin} onChange={(event) => updateBlock(block.key, { ingredients: block.ingredients.map((item) => item.key === row.key ? { ...item, quantityMin: event.target.value } : item) })} /></Field>
                          <Field label="Maximum"><input className="input" inputMode="decimal" value={row.quantityMax} onChange={(event) => updateBlock(block.key, { ingredients: block.ingredients.map((item) => item.key === row.key ? { ...item, quantityMax: event.target.value } : item) })} /></Field>
                          <Field label="Unit"><input className="input" value={row.unit} onChange={(event) => updateBlock(block.key, { ingredients: block.ingredients.map((item) => item.key === row.key ? { ...item, unit: event.target.value } : item) })} /></Field>
                          <Field label="Food"><input className="input" value={row.food} onChange={(event) => updateBlock(block.key, { ingredients: block.ingredients.map((item) => item.key === row.key ? { ...item, food: event.target.value } : item) })} /></Field>
                          <Field label="Preparation"><input className="input" value={row.preparation} onChange={(event) => updateBlock(block.key, { ingredients: block.ingredients.map((item) => item.key === row.key ? { ...item, preparation: event.target.value } : item) })} /></Field>
                          <label className="ingredient-row__optional"><Checkbox checked={row.optional} onCheckedChange={(checked) => updateBlock(block.key, { ingredients: block.ingredients.map((item) => item.key === row.key ? { ...item, optional: checked === true } : item) })} />Optional ingredient</label>
                        </div>
                      </details>
                    </div>
                    <ReorderActions
                      label={label}
                      index={rowIndex}
                      length={block.ingredients.length}
                      onMove={(to) => updateBlock(block.key, { ingredients: moveAt(block.ingredients, rowIndex, to) })}
                      onRemove={() => updateBlock(block.key, { ingredients: block.ingredients.length === 1 ? [newIngredient()] : block.ingredients.filter((item) => item.key !== row.key) })}
                    />
                  </article>
                );
              })}
            </div>
            <Button type="button" variant="ghost" onClick={() => updateBlock(block.key, { ingredients: [...block.ingredients, newIngredient()] })}><Plus aria-hidden="true" />Add ingredient</Button>
          </section>
        ))}
      </div>
      <Button type="button" variant="secondary" onClick={() => setBlocks((current) => [...current, newEditorBlock("")])}><Plus aria-hidden="true" />Add a component</Button>
    </section>
  );
}

export function StructuredMethodEditor({
  blocks,
  setBlocks,
  onRowsSplit,
}: {
  blocks: EditorBlock[];
  setBlocks: SetBlocks;
  onRowsSplit: (previous: EditorBlock[], count: number, kind: "ingredients" | "steps") => void;
}) {
  function updateSteps(blockKey: string, instructions: EditorBlock["instructions"]) {
    setBlocks((current) => current.map((block) => block.key === blockKey ? { ...block, instructions } : block));
  }

  function pasteLines(event: ClipboardEvent<HTMLTextAreaElement>, block: EditorBlock, stepIndex: number) {
    if (block.instructions[stepIndex]?.text.trim()) return;
    const lines = splitPastedRows(event.clipboardData.getData("text"));
    if (lines.length < 2) return;
    event.preventDefault();
    const previous = blocks;
    const replacement = lines.map((text) => newMethodStep(text));
    updateSteps(block.key, [...block.instructions.slice(0, stepIndex), ...replacement, ...block.instructions.slice(stepIndex + 1)]);
    onRowsSplit(previous, replacement.length, "steps");
  }

  return (
    <section className="structured-workbench recipe-editor__method-workbench" aria-labelledby="structured-method-heading">
      <header className="structured-workbench__heading">
        <div><p className="eyebrow">Method</p><h2 id="structured-method-heading">Give every step room to breathe</h2><p>Keep each action separate so it stays readable on the counter and in Cook Mode.</p></div>
        <span>{blocks.reduce((total, block) => total + block.instructions.filter((step) => step.text.trim()).length, 0)} steps</span>
      </header>
      <div className="structured-components">
        {blocks.map((block, blockIndex) => (
          <section className="structured-component method-component" key={block.key} aria-label={`${blockName(block, blockIndex)} method`}>
            <header className="structured-component__heading"><div><strong>{blockName(block, blockIndex)}</strong><small>{blockIndex === 0 ? "Main method" : "Component method"}</small></div></header>
            <div className="method-steps">
              {block.instructions.map((step, stepIndex) => {
                const label = `step ${stepIndex + 1} for ${blockName(block, blockIndex)}`;
                return (
                  <article className="method-step" key={step.key}>
                    <span className="method-step__number" aria-hidden="true">{stepIndex + 1}</span>
                    <label><span className="visually-hidden">{label}</span><textarea className="input textarea" value={step.text} onChange={(event) => updateSteps(block.key, block.instructions.map((item) => item.key === step.key ? { ...item, text: event.target.value } : item))} onPaste={(event) => pasteLines(event, block, stepIndex)} placeholder={stepIndex === 0 ? "Season generously, then heat a wide pan." : "Add the next step"} /></label>
                    <ReorderActions
                      label={label}
                      index={stepIndex}
                      length={block.instructions.length}
                      onMove={(to) => updateSteps(block.key, moveAt(block.instructions, stepIndex, to))}
                      onRemove={() => updateSteps(block.key, block.instructions.length === 1 ? [newMethodStep()] : block.instructions.filter((item) => item.key !== step.key))}
                    />
                  </article>
                );
              })}
            </div>
            <Button type="button" variant="ghost" onClick={() => updateSteps(block.key, [...block.instructions, newMethodStep()])}><Plus aria-hidden="true" />Add step</Button>
          </section>
        ))}
      </div>
    </section>
  );
}
