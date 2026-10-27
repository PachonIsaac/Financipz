# Financipz frontend

Mobile-first PWA built with Vite, React, TypeScript, Tailwind CSS and TanStack Query.

## Run

```bash
cp .env.example .env   # fill in the auth settings
npm install
npm run dev            # http://localhost:5173
```

Other scripts: `npm run build`, `npm test`, `npm run lint`, `npm run typecheck`.

## Environment

See `.env.example`. `VITE_BASE` sets the sub-path the app is served from (default `/`).
Authentication uses the auth client only for sign in, sign out and token refresh; all data
comes from the backend REST API with a bearer token.

## Icons

`node scripts/generate-icons.mjs` regenerates the PNG icons in `public/`.
