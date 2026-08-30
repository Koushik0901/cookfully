# Visual regression baselines

Every `captureUi` call is a strict Playwright screenshot assertion. The committed baselines cover the
desktop Chromium and 390 × 844 touch layouts, using mocked and fixed fixtures from the owning E2E test.

Run the checks with:

```powershell
pnpm --dir frontend e2e
```

When an intentional, reviewed UI change changes a screenshot, regenerate only after verifying it in the
browser:

```powershell
pnpm --dir frontend e2e:visual:update
```

Baselines live under `frontend/e2e/__screenshots__/`, are committed, and use CSS-pixel scale with motion
and carets disabled. Do not accept a changed image without reviewing the relevant route and state.

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
