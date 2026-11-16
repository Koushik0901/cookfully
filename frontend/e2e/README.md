# Visual regression baselines

Every `captureUi` call is a strict Playwright screenshot assertion. The committed baselines cover the
desktop Chromium and 390 × 844 touch layouts, using mocked and fixed fixtures from the owning E2E test.

Font rasterisation differs between operating systems, so every platform owns its baselines. The
platform is part of the file name:

| Suffix | Rendered on | Used by |
| --- | --- | --- |
| `-linux.png` | GitHub Actions (Ubuntu) | CI |
| `-win32.png` | A Windows developer machine | local `pnpm e2e` on Windows |
| `-darwin.png` | A Mac | local `pnpm e2e` on macOS |

Run the checks with:

```powershell
pnpm --dir frontend e2e
```

## Updating baselines

When an intentional, reviewed UI change alters a screenshot:

1. **Linux (CI):** run the **Update visual baselines** workflow from the Actions tab on your branch. It
   regenerates every `-linux.png` and commits them to the branch. Review the images in that commit.
2. **Your own machine:** `pnpm --dir frontend e2e:visual:update` regenerates the baselines for your
   platform only.

Do not accept a changed image without reviewing the relevant route and state.

CI compares pixels only once `-linux.png` baselines exist. Until then it prints a warning and still runs
every behavioural assertion, so the first run of the workflow above is what switches visual checks on.

## How CI runs these tests

CI serves the production bundle (`vite preview`) after `pnpm build`, with two workers, and uploads the
Playwright report when a run fails. Locally, the dev server is used. The time zone is pinned to UTC so
dates render identically everywhere; specs that show "today" must still freeze the clock with
`page.clock`.

## Native select policy

Cookfully uses semantic native `<select>` elements. The closed control is owned by Cookfully: it has the
shared input geometry, label, focus state, and a decorative chevron. The opened option list is
intentionally platform-native so keyboard, touch, accessibility, and mobile picker behavior remain
reliable.

Chromium desktop and 390 × 844 touch layouts are the committed pixel baselines. Native option popups are
not pixel-baselined because WebKit, Windows, and mobile operating systems render them differently. The
focused `webkit-native-select` Playwright project verifies the native element, accessible name, minimum
closed-control geometry, and selection behavior instead:

```powershell
pnpm --dir frontend exec playwright test --project=webkit-native-select
```
