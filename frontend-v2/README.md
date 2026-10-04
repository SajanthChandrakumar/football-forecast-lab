# Football Forecast Lab frontend

React, TypeScript and Vite. Development API requests are proxied to the local backend on port 8000.

```sh
npm ci
npm run dev
```

## Verification

```sh
node --test tests/*.test.mjs
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests use the production build, serve it on 127.0.0.1:4173 and intercept API requests with disposable fixtures. They never connect to MongoDB or external data providers. Build before running them; the test runner rejects an already occupied preview port.

The suite covers tips and retries, deadline handling, competition switching, persistent team comparison, request and browser-storage failures, keyboard navigation and both themes at 375, 390, 768 and 1440 pixels. The fixtures use a fixed clock and independent state for every test. They validate frontend behavior; backend integration is covered separately by pytest.

On failure, Playwright saves screenshots, traces and an HTML report. GitHub Actions runs the same suite and retains failure diagnostics for seven days.

```sh
npx playwright show-report
npm run test:e2e -- --project=phone-375
```
