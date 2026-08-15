# Cookfully Design & UX Constitution

> **This file is a product requirement, not aesthetic inspiration.**
>
> Any coding agent modifying user-facing UI must read and follow this document before making changes.

---

## 1. Product Experience

Cookfully is a **cooking and meal-planning application that understands nutrition**.

It is **not** a nutrition tracker that happens to contain recipes.

The product exists to help people:

**Discover → Plan → Prep → Shop → Cook → Eat well**

Cookfully is for anyone trying to take better control of their health through food:

- people who want to eat balanced meals,
- people trying to meet nutritional needs,
- people meal-prepping,
- people cutting or bulking,
- people trying to get in shape,
- people trying to eat cleaner,
- people organizing household meals,
- people who simply want to cook better food with less friction.

Do not optimize the experience primarily for gym culture, calorie obsession, bodybuilding, or macro logging.

Nutrition is important, but it should usually behave like **quiet intelligence underneath the cooking experience**.

### Core product principle

> **Food is the primary object. Nutrition is supporting intelligence.**

When choosing between showing food or showing numbers, prefer food unless the numbers are necessary for the user's current task.

---

# 2. Experience Personality

Cookfully should feel:

- calm,
- warm,
- appetizing,
- thoughtful,
- capable,
- modern,
- personal,
- polished,
- quietly intelligent,
- encouraging without being patronizing.

Cookfully should **not** feel:

- clinical,
- gym-bro oriented,
- administrative,
- database-like,
- spreadsheet-like,
- enterprise-software-like,
- configuration-heavy,
- developer-facing,
- sterile,
- visually empty,
- cluttered,
- aggressively gamified.

The user should feel like they are using a polished consumer application, not managing a database.

---

# 3. The First Question on Every Screen

Before designing or modifying a page, answer:

> **What is the user trying to accomplish here?**

Then identify:

1. the primary user goal,
2. the primary object,
3. the primary action,
4. secondary actions,
5. information required right now,
6. information that can be hidden,
7. complexity the system can absorb,
8. what success looks like.

Do **not** begin with:

> "What information can we display here?"

A page should exist to help the user accomplish something.

---

# 4. UX Decision Hierarchy

When principles conflict, use this priority order:

1. **User comprehension**
2. **Task completion**
3. **Reduced cognitive load**
4. **Accessibility**
5. **Consistency and familiar mental models**
6. **Responsiveness**
7. **Visual hierarchy**
8. **Aesthetic polish**
9. **Delight**
10. **Novelty**

Never sacrifice usability for visual novelty.

Never sacrifice accessibility for aesthetics.

Never keep a confusing interaction merely because it looks sophisticated.

---

# 5. Core UX Laws as Implementation Rules

These principles are inspired by established interaction-design and human-factors research. They must be applied as **decision rules**, not decorative theory.

---

## 5.1 Cognitive Load

### Rule

Do not require the user to think about information that is irrelevant to their current task.

The interface should externalize memory wherever possible.

### Implementation requirements

- Remove implementation details from normal user flows.
- Do not expose internal identifiers, persistence models, database terminology, technical state names, or infrastructure details unless the user explicitly needs them.
- Prefer recognition over recall.
- Preserve context between steps.
- Remember user choices when appropriate.
- Use sensible defaults.
- Avoid forcing the user to mentally compare distant information.
- Avoid long unstructured forms.
- Avoid large numbers of equally prominent controls.
- Avoid asking for information the system can infer.

### Cookfully examples

Bad:

- showing `America/Vancouver` at the top of Plan,
- explaining immutable database snapshots to normal users,
- forcing users to calculate serving allocations mentally,
- displaying nutrition-source internals as primary recipe information.

Better:

- show the week,
- show meals,
- show servings,
- show useful nutrition insight only when relevant,
- keep technical details invisible unless needed.

---

## 5.2 Hick's Law / Choice Overload

### Rule

The more choices users must evaluate simultaneously, the harder the interface becomes.

### Implementation requirements

When many options exist:

- choose sensible defaults,
- recommend likely choices,
- group related options,
- sequence complex workflows,
- progressively disclose advanced functionality,
- prioritize one primary action,
- move rare actions into secondary menus.

Do not solve complexity by simply placing twenty controls into one dropdown.

Before adding a button, filter, field, tab, chip, or setting, ask:

> **Does this need to be visible at this moment?**

---

## 5.3 Jakob's Law / Familiar Mental Models

### Rule

Use interaction patterns people already understand unless deviation creates meaningful user value.

Innovation belongs primarily in what Cookfully helps people accomplish, not in reinventing basic interface behavior.

### Requirements

- Search should behave like search.
- Tabs should behave like tabs.
- Filters should look and behave like filters.
- Checkboxes must look selectable.
- Links must look interactive.
- Drag-and-drop must have obvious affordances.
- Back navigation should behave predictably.
- Common mobile navigation should follow familiar patterns.
- Destructive actions must use conventional warning patterns.

Do not invent unfamiliar controls merely to look unique.

---

## 5.4 Fitts's Law

### Rule

Important and frequent actions must be easy to target.

### Requirements

- Primary actions receive generous click/touch targets.
- Mobile controls must be comfortably tappable.
- Avoid tiny icon-only hit targets.
- Do not place commonly used actions in hard-to-reach locations.
- Clicking labels should activate associated inputs when appropriate.
- Frequently repeated actions should require minimal pointer travel.

Examples:

- Add meal
- Add to week
- Cook
- Mark ingredient complete
- Add grocery item
- Change servings

These should never feel fiddly.

---

## 5.5 Proximity

### Rule

Things that belong together should be physically near one another.

### Requirements

- Controls should live next to the content they modify.
- Related labels, values, and actions should form visually coherent groups.
- Large gaps imply separation.
- Small gaps imply relationship.
- Do not rely on borders to compensate for poor spacing logic.

Example:

Serving controls belong beside the meal or recipe they affect, not in a distant settings area.

---

## 5.6 Common Region

### Rule

Containers should communicate meaningful grouping.

### Requirements

Use cards, panels, backgrounds, or borders only when they clarify:

- ownership,
- grouping,
- hierarchy,
- interaction,
- or separation.

Do not "cardify" every section.

Avoid dashboards made from dozens of bordered rectangles.

Prefer spacing and typography when they are sufficient.

---

## 5.7 Similarity

### Rule

Elements with the same visual treatment should behave similarly.

### Requirements

- Primary actions should share a consistent treatment.
- Destructive actions should be visually distinct.
- Tertiary actions should not compete with primary actions.
- Interactive text must be distinguishable from static text.
- Selected states must be consistently represented.
- Status colors must mean the same thing throughout the application.

Never reuse a strong primary-button style for unrelated low-priority actions.

---

## 5.8 Tesler's Law / Conservation of Complexity

### Rule

Some complexity is unavoidable. Whenever Cookfully can reasonably absorb that complexity, the system should handle it instead of the user.

### Requirements

Prefer system intelligence for:

- nutrition calculations,
- serving math,
- grocery consolidation,
- unit normalization,
- leftovers,
- repeated meals,
- shared ingredient preparation,
- pantry subtraction,
- week balancing,
- recommendation ranking,
- recipe parsing,
- URL import cleanup,
- common defaults.

Do not push implementation complexity onto the user because it is easier to code.

A more complex backend can be justified if it creates a meaningfully simpler experience.

---

## 5.9 Aesthetic-Usability Effect

### Rule

Beauty matters because it influences trust and perceived ease, but visual polish must support real usability.

### Requirements

Invest in:

- typography,
- whitespace,
- food imagery,
- hierarchy,
- color,
- responsive composition,
- high-quality icons,
- thoughtful empty states,
- loading states,
- transitions,
- micro-interactions.

But never use aesthetic polish to hide:

- poor information architecture,
- confusing controls,
- excessive complexity,
- broken responsiveness,
- inaccessible patterns.

A beautiful confusing interface is still a failed interface.

---

## 5.10 Peak-End Rule

### Rule

Pay special attention to meaningful moments and endings.

### Candidate Cookfully moments

- recipe successfully imported,
- first meal added to a week,
- weekly plan completed,
- grocery list generated,
- prep session completed,
- recipe successfully cooked,
- nutrition goal reached naturally through planning.

These moments can receive subtle delight:

- satisfying motion,
- encouraging copy,
- visual acknowledgement,
- useful next-step suggestions.

Do not use celebration for trivial actions.

---

## 5.11 Doherty Threshold / Responsiveness

### Rule

The interface must acknowledge actions immediately.

### Requirements

When work is fast:

- update immediately.

When work takes noticeable time:

- show immediate feedback,
- show meaningful progress when possible,
- use skeletons where structure is known,
- preserve context,
- avoid blank loading screens.

Never leave the user wondering whether their action worked.

Example:

Recipe URL import should immediately transition into a meaningful processing state rather than appearing frozen.

---

## 5.12 Von Restorff Effect

### Rule

Visual emphasis should be scarce.

If everything is emphasized, nothing is emphasized.

### Requirements

- Limit strong accent color usage.
- Use one dominant primary action per local context whenever possible.
- Reserve badges for meaningful states.
- Avoid many competing bright buttons.
- Use scale and typography before adding more color.

---

## 5.13 Serial Position

### Rule

People tend to notice and remember items at the beginning and end more than those buried in the middle.

### Requirements

- Put important navigation destinations in high-salience positions.
- Keep rare/admin functionality out of primary navigation.
- Place primary actions where users naturally scan.
- In lists, think deliberately about ordering.

---

## 5.14 Goal Gradient

### Rule

Visible progress toward a meaningful goal can motivate continued completion.

### Requirements

Use progress only when the goal matters to the user.

Good examples:

- 5 of 7 dinners planned,
- 3 prep tasks left,
- grocery list 80% checked,
- 2 meals still need planning.

Avoid meaningless gamification.

Do not invent streaks, points, badges, or progress bars unless they serve the user's actual goal.

---

## 5.15 Postel's Law / Forgiving Input

### Rule

Accept reasonable variation from the user and normalize it internally.

### Requirements

Be flexible about:

- recipe URLs,
- pasted recipe text,
- ingredient formats,
- units,
- capitalization,
- whitespace,
- common abbreviations.

Produce predictable, normalized output.

The user should not need to understand Cookfully's internal schema before entering food.

---

## 5.16 Selective Attention

### Rule

Users notice what is relevant to their current goal and ignore much of everything else.

### Requirements

The current task should dominate the screen.

Examples:

During Cook Mode:

- ingredients,
- quantities,
- steps,
- timers,
- servings

should dominate.

Administrative metadata, nutrition provenance, recipe management, and secondary navigation should recede.

---

## 5.17 Working Memory and Chunking

### Rule

Do not expect people to hold large amounts of information in working memory.

### Requirements

Break complex information into meaningful chunks.

Examples:

Ingredients may be grouped by:

- sauce,
- marinade,
- filling,
- garnish,
- main dish.

Settings should be grouped by human purpose, not backend architecture.

Planning should be grouped by:

- day,
- meal,
- prep action,
- grocery need.

Do not present long undifferentiated walls of information.

---

## 5.18 Occam's Razor

### Rule

When two solutions work equally well, prefer the one with the simpler mental model.

Examples:

Prefer:

- dragging a recipe onto Tuesday,

over:

- opening a modal,
- selecting an allocation entity,
- selecting a date,
- choosing a slot type,
- confirming,
- returning to the planner.

Do not expose unnecessary domain abstractions.

---

## 5.19 Paradox of the Active User

### Rule

Assume users will start using Cookfully without reading documentation.

### Requirements

The interface should teach itself through:

- clear labels,
- contextual hints,
- good defaults,
- useful empty states,
- familiar controls,
- progressive onboarding.

Documentation should support the product, not compensate for confusing design.

---

# 6. Information Architecture

Cookfully's primary experience should map to the user's food workflow.

Preferred conceptual flow:

**Recipes → Plan → Prep → Grocery → Cook**

Other capabilities should support this loop.

Do not create a primary navigation destination merely because a backend feature exists.

A capability may be better expressed contextually.

Example:

"Suggestions" should not necessarily be a permanent top-level page.

Instead:

- Recipes can offer **Give me ideas**.
- Plan can offer **Help fill this week**.
- Pantry can offer **What can I make?**

The capability follows the user's intent.

---

# 7. Page-Specific Product Principles

---

## 7.1 Recipes

Recipes is not a database table.

It is a discovery and organization surface.

Primary questions:

- What do I want to cook?
- Can I find a saved recipe quickly?
- Can I discover something suitable?
- Can I understand whether a recipe fits my needs?

Recipes should support:

- strong search,
- useful sorting,
- human-centered filters,
- saved groups/collections when helpful,
- visual browsing,
- contextual inspiration.

Avoid making database-processing states the main filtering model.

Examples of useful filters may include:

- meal type,
- cuisine,
- dietary preference,
- preparation time,
- protein source,
- calories,
- protein,
- tags,
- favorites,
- recently cooked,
- planned soon.

Food imagery should usually lead recipe cards.

Nutrition should be readable but secondary.

---

## 7.2 Plan

Plan is a **weekly meal-planning workspace**, not a macro dashboard.

The primary object is:

> **the week of meals**

The default experience should help the user answer:

- What am I eating?
- Which days are handled?
- What needs planning?
- What should I prep?
- What groceries will I need?

Meal cards should emphasize:

- food,
- dish name,
- servings,
- meal placement,
- leftovers,
- prep state.

Nutrition is a supporting layer.

It may summarize:

- weekly balance,
- protein sufficiency,
- calorie range,
- fiber,
- other meaningful nutritional observations.

It should not dominate the planner unless the user explicitly opens detailed nutrition.

Preferred hierarchy:

**Food → Week → Prep → Grocery → Nutrition insight**

Not:

**Macros → Targets → Progress bars → Meals**

### Meal-prep intelligence

Cookfully should eventually support the mental model:

> **Cook once → eat multiple times**

Example:

Chicken Tikka Masala — 6 servings

- Monday dinner — 2
- Tuesday lunch — 1
- Wednesday dinner — 2
- 1 serving remaining

This is more useful than treating every meal slot as an unrelated database entry.

---

## 7.3 Prep

Prep should answer:

> **What can I do ahead of time to make this week easier?**

Potential outputs:

- cook rice,
- roast vegetables,
- marinate chicken,
- chop shared ingredients,
- prepare sauces,
- batch breakfast,
- portion leftovers.

Cookfully should identify repeated ingredients and overlapping preparation when possible.

The user should not manually discover every opportunity for batching.

---

## 7.4 Grocery

The grocery experience should emerge naturally from the plan.

Cookfully should:

- consolidate ingredient quantities,
- account for servings,
- subtract pantry items when appropriate,
- group items meaningfully,
- support quick checking,
- preserve an easy path back to the meals requiring an item.

A grocery list is a user tool, not a raw ingredient export.

---

## 7.5 Cook Mode

Cook Mode is a focused environment.

The screen should prioritize:

1. current step,
2. ingredients relevant to the step,
3. quantities,
4. timers,
5. progression.

Avoid unrelated information.

Touch targets should be large.

The interface should remain useful with messy hands and divided attention.

---

## 7.6 Goals & Nutrition

Goals should feel like guidance, not configuration.

Avoid giant forms.

Ask only what is useful.

Use:

- clear explanations,
- sensible defaults,
- progressive disclosure,
- contextual examples.

A person who simply wants to "eat healthier" should not be forced to understand every macro concept before using Cookfully.

Advanced users may configure detailed targets, but advanced configuration should not dominate the default experience.

---

# 8. Progressive Disclosure

Secondary and advanced information should appear only when it becomes useful.

Use progressive disclosure for:

- advanced nutrition,
- recipe provenance,
- detailed metadata,
- technical configuration,
- integrations,
- expert controls,
- rarely used filters,
- destructive management operations.

Do not hide frequently needed functionality just to make the interface look minimal.

Minimalism is not the goal.

**Appropriate information density is the goal.**

---

# 9. Visual Hierarchy

Every screen must answer visually:

1. Where am I?
2. What is this screen for?
3. What should I look at first?
4. What can I do?
5. What is secondary?

Use hierarchy through:

- typography,
- scale,
- spacing,
- layout,
- imagery,
- contrast,
- restrained color.

Avoid solving hierarchy entirely with:

- borders,
- cards,
- badges,
- background blocks.

---

# 10. Typography

Typography should feel warm, modern, editorial, and highly readable.

Requirements:

- clear distinction between display, heading, body, label, and metadata,
- comfortable line length,
- readable line height,
- no tiny metadata text,
- avoid excessive font weights,
- avoid all-caps except rare compact labels,
- use tabular numerals only where numeric comparison benefits.

Food names and primary content should have more personality than infrastructure labels.

---

# 11. Color

Cookfully's color system should reinforce food, wellbeing, and calmness.

Use accent color deliberately.

Color must communicate consistently:

- primary action,
- success,
- warning,
- destructive action,
- selection,
- informational state.

Do not rely on color alone.

Avoid turning nutrition into a rainbow dashboard unless color serves a specific comparison task.

Strong color should be scarce enough to remain meaningful.

---

# 12. Imagery

Food imagery is a major part of Cookfully's product language.

Where useful:

- recipe cards,
- discovery,
- planning,
- cooking history,
- suggestions.

Images should support recognition and appetite, not act as decoration.

Avoid generic lifestyle imagery that does not help the user understand the food.

Fallback states should still feel deliberate and polished.

---

# 13. Spacing

Spacing communicates structure.

Use spacing before borders.

Related items:

- closer together.

Different groups:

- further apart.

Major page regions:

- clear separation.

Do not create giant empty areas that make the application feel unfinished.

Do not compress unrelated content merely to fit more above the fold.

---

# 14. Cards

Cards are not the default answer.

Use a card when content represents a meaningful standalone object or region.

Good candidates:

- a recipe,
- a planned meal,
- a suggestion,
- an actionable insight.

Weak candidates:

- every paragraph,
- every metric,
- every setting,
- every label/value pair.

Avoid the "dashboard of rounded rectangles" aesthetic.

---

# 15. Forms

Large form walls are a major Cookfully anti-pattern.

### Requirements

- Ask only for what is needed.
- Group fields meaningfully.
- Use strong defaults.
- Reveal advanced fields progressively.
- Use inline validation.
- Preserve entered values.
- Explain unfamiliar concepts near the field.
- Avoid placeholder-only labels.
- Provide human-readable units and examples.

Recipe creation should feel like creating food, not completing a government form.

---

# 16. Filters

Filters should support real user intents.

Do not expose internal state simply because it exists in the database.

A filter interface should:

- surface the most useful filters first,
- show active filters clearly,
- make clearing filters easy,
- preserve search context,
- support combinations without becoming overwhelming.

Secondary filters can live behind **More filters**.

Mobile filtering may use a dedicated sheet or modal if it improves usability.

---

# 17. Navigation

Primary navigation must be intentionally small.

A destination deserves permanent navigation only if users frequently think of it as a distinct place they want to go.

Do not mirror backend modules.

Keep:

- common destinations prominent,
- contextual actions contextual,
- administrative or rare functionality secondary.

On mobile, primary destinations must remain reachable without awkward overflow.

---

# 18. Empty States

An empty state should answer:

1. What is this?
2. Why is it useful?
3. What should I do next?

Do not show:

> "No data."

Prefer specific language.

Example:

> **Nothing planned for Wednesday yet.**  
> Add one of your recipes or let Cookfully suggest something that fits the rest of your week.

Empty states should provide momentum.

---

# 19. Loading States

Avoid blank screens.

Use:

- skeletons for predictable content,
- progress indicators for longer work,
- optimistic updates where safe,
- contextual loading copy for meaningful processes.

Do not use fake progress precision.

Never block the entire application when only a local region is loading.

---

# 20. Errors

Errors should help recovery.

Bad:

> Error 422.

Better:

> We couldn't import that recipe. The page may block automated access. You can paste the recipe text instead.

Error messages should explain:

- what happened,
- what the user can do,
- whether their work was preserved.

Never expose stack traces or backend terminology to normal users.

---

# 21. Confirmation & Destructive Actions

Do not ask for confirmation for harmless reversible actions.

Confirm when:

- deletion is difficult to recover,
- data loss is likely,
- consequences are meaningful.

Prefer undo for reversible actions.

Destructive actions must be clearly differentiated.

---

# 22. Motion

Motion should explain relationships and state changes.

Use motion for:

- entering/exiting layers,
- reordering,
- completion,
- selection,
- state transitions.

Avoid decorative movement that competes with food or task content.

Motion should be:

- short,
- purposeful,
- interruptible,
- respectful of reduced-motion preferences.

---

# 23. Micro-interactions

Small interaction details matter.

Every interactive component should consider:

- default,
- hover,
- focus,
- active/pressed,
- selected,
- loading,
- disabled,
- error,
- success.

Native controls that visually clash with the product should be styled through accessible primitives rather than hacked replacements.

---

# 24. Responsive Design

Responsive design is not desktop UI squeezed into a smaller width.

For each page, determine what matters most on mobile.

### Requirements

- preserve task hierarchy,
- reduce simultaneous secondary controls,
- provide appropriate bottom navigation or contextual navigation,
- use sheets/drawers where they improve focus,
- preserve generous touch targets,
- avoid horizontal scrolling for primary workflows,
- ensure modals fit small screens,
- ensure keyboards do not obscure critical fields/actions.

Test at realistic phone dimensions.

---

# 25. Accessibility

Accessibility is a baseline requirement.

### Required

- semantic HTML,
- keyboard-completable workflows,
- visible focus,
- accessible names,
- correctly associated labels,
- sufficient contrast,
- touch-friendly targets,
- reduced-motion support,
- meaningful heading hierarchy,
- screen-reader-friendly state changes where relevant.

Do not replace accessible native behavior with custom visuals unless the replacement remains fully accessible.

---

# 26. UX Writing

Cookfully's language should feel human, concise, and useful.

Prefer:

- "Add a meal"
- "Use leftovers"
- "Give me ideas"
- "Help fill this week"
- "Make grocery list"
- "Prep this week"
- "Cook this"

Avoid unnecessarily technical language such as:

- immutable snapshots,
- nutrition provenance state,
- allocation entities,
- owner scope,
- database records,
- synchronization objects.

Write for the person cooking dinner, not the engineer maintaining the service.

---

# 27. Settings Philosophy

Settings are a last resort.

Before adding a setting, ask:

> Can Cookfully make a good default decision instead?

If yes, prefer the default.

Settings should represent meaningful user preferences, not expose implementation choices.

Advanced technical configuration should be clearly separated from everyday preferences.

---

# 28. Design Consistency

Before creating a new component, inspect existing components.

Prefer reusing or extending established patterns for:

- buttons,
- inputs,
- checkboxes,
- chips,
- tabs,
- dialogs,
- sheets,
- dropdowns,
- cards,
- feedback,
- loading,
- empty states.

Do not create slightly different versions of the same interaction on every page.

Consistency reduces learning cost.

---

# 29. Anti-Patterns

Avoid these unless there is a very strong reason.

### UI anti-patterns

- giant form walls,
- raw HTML controls inconsistent with the design system,
- dozens of equal-priority cards,
- excessive borders,
- excessive pills/badges,
- tiny icon buttons,
- huge empty whitespace with little purpose,
- dashboards full of metrics,
- nested modals,
- overly long sidebars,
- dense settings pages,
- hidden core functionality,
- unexplained icons,
- excessive gradients,
- decorative glassmorphism,
- unnecessary floating elements,
- auto-playing motion.

### UX anti-patterns

- exposing implementation details,
- asking users to configure things the app can infer,
- requiring documentation for basic use,
- forcing users to remember information between screens,
- too many decisions at once,
- invisible system status,
- destructive actions without recovery,
- surprising navigation,
- making users manage backend abstractions.
