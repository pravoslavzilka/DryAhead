# frontend/

React + Vite. **Plain JavaScript/JSX, not TypeScript** — the root README
claims TS, but there is no `tsconfig.json` anywhere and every source file
is `.jsx`/`.js`. Trust the code over that README line.

## State, not aspiration
- Package manager: npm (`package-lock.json`). Verified scripts (from
  `package.json`): `dev` (`vite`), `build` (`vite build`), `preview`
  (`vite preview`). **No `test`, `lint`, or `format` script exists.**
- No test framework installed (no Vitest/Jest/Playwright), no ESLint
  config, no Prettier config.
- Deployed to Vercel from this subdirectory via the Vercel dashboard's
  Root Directory setting — there is no `vercel.json` in-repo confirming
  this; it's UNVERIFIED from the repo alone.
- `.env` holds only the Supabase **anon** key and is gitignored — never the
  `service_role` key, never commit it even temporarily.
