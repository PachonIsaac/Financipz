# Financipz frontend

Mobile-first PWA built with Vite, React, TypeScript, Tailwind CSS and TanStack Query. Dark only, with an orange accent; icons come from `lucide-react`.

## Screens

Home (balance, month summary with a chart, spending by category, accounts, latest movements), Movements (grouped by day, with filters), New movement, Review (movements that arrived from the bank or the wallet and wait to be confirmed, with the account and the class of a transfer to be chosen when the notification did not say), Accounts (including leaving an account out of the balance), Categories (color and icon), Crypto and the exchange connection, the mailbox connection, and the iOS shortcut token.

The app asks the API for its health as soon as it opens, so a sleeping server wakes while the person signs in; a notice shows the elapsed time and the last wake-up durations are kept on the device (More screen).

## Run

```bash
cp .env.example .env   # fill in the auth settings
npm install
npm run dev            # http://localhost:5173
```

Other scripts: `npm run build`, `npm test`, `npm run lint`, `npm run typecheck`. The test environment cannot use the browser storage that Node provides, so tests that need it use `stubLocalStorage` from `src/test/utils.tsx`.

## Environment

See `.env.example`: `VITE_API_URL` (the API, ending in `/api/v1`), `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` (sign in only; the publishable key is public by design), and `VITE_BASE`, the sub-path the app is served from (default `/`). Production builds fail unless `VITE_API_URL` is set; in development it defaults to the local backend. For a static host without rewrites, copy `dist/index.html` to `dist/404.html` so a reload on an inner route works.
Authentication uses the auth client only for sign in, sign out and token refresh; all data
comes from the backend REST API with a bearer token.

## Icons

`node scripts/generate-icons.mjs` regenerates the PNG icons in `public/`.
