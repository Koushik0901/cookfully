# Recipe Library Desktop Density

**Date:** 2026-08-16
**Status:** Approved direction, pending written-spec review

## Problem

At wide desktop sizes, the authenticated recipe library's content frame is capped at `90rem` while
the navigation rail remains fixed. The result is a visually narrow three-column library surrounded by
unused canvas. The cards, header, search, and discovery controls read as a centered island instead of
a confident use of the available workspace.

## Goal

Use more of the desktop canvas without changing the recipe-library interaction model or making the
page feel like a dense data dashboard. Recipe imagery and titles remain the dominant content, while
nutrition stays a compact evidence layer.

## Chosen Approach: Wider Three-Column Frame

Increase the desktop `.page-shell` maximum width from `90rem` to approximately `100rem`. Keep the
existing horizontal page inset and allow all library regions to expand together:

- page header and actions;
- search field and view tabs;
- filter disclosure and collection strip;
- active-filter feedback;
- recipe groups and their three-column card grids.

The existing three-column grid remains the desktop composition. Card proportions, image-first order,
4:3 media, card metadata, nutrition ribbon, menu placement, and interaction states do not change.

## Responsive Behavior

- Desktop: use the wider frame when space allows and retain three columns.
- Tablet: retain the existing two-column breakpoint and compact navigation rail.
- Mobile: retain the existing one-column grid, mobile page inset, top brand bar, and bottom navigation.
- The wider desktop maximum must not introduce document-level horizontal overflow at any breakpoint.

No new featured-card ranking, four-column mode, or content-model change is part of this work.

## Accessibility and States

The change is layout-only and must preserve existing semantic and interaction contracts:

- keyboard focus order and visible focus rings remain unchanged;
- recipe cards remain reachable through their existing links and menus;
- long titles continue to clamp without escaping their card;
- loading, empty, partial, estimated, manual, stale, failed, archived, and unavailable states retain
  their current presentation;
- images continue to use useful alt text or the existing food-specific fallback art.

## Verification

Review the recipe library at `1440x900`, a wide desktop viewport, and `390x844`.

Confirm that:

1. the desktop side field is visibly reduced;
2. the three-column cards remain comfortably readable and image-led;
3. header, discovery controls, and grid share aligned content edges;
4. tablet and mobile layouts remain coherent;
5. keyboard navigation and focus visibility are intact;
6. long titles, missing images, and nutrition states do not create overflow;
7. frontend lint, typecheck, tests, and build pass.
