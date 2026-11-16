# Visual regression baselines

Every `captureUi` call is a strict Playwright screenshot assertion. The committed baselines cover the
desktop Chromium and 390 × 844 touch layouts, using mocked and fixed fixtures from the owning E2E test.

Baselines live under `frontend/e2e/__screenshots__/`, are committed, and use CSS-pixel scale with motion
and carets disabled. Do not accept a changed image without reviewing the relevant route and state.

## Baselines are rendered on Linux, in CI

Pixels depend on the operating system's font rasterisation, so a baseline only matches where it was
rendered. CI runs on Linux, therefore **the committed baselines are Linux renders** produced by the
`Update visual baselines` workflow, not images captured on a developer machine.

To regenerate after an intentional, reviewed UI change:

1. Push the branch, then run the `Update visual baselines` workflow on it from the Actions tab (or push a
   branch named `visual-baselines/<anything>`).
2. Download and review the images, then commit them:

   ```bash
   gh run download <run-id> --name visual-baselines --dir frontend/e2e/__screenshots__
   ```

Running the suite locally on Windows or macOS will report pixel differences that CI will not. To check
behaviour without pixels, run:

```powershell
pnpm --dir frontend exec playwright test --ignore-snapshots
```

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
