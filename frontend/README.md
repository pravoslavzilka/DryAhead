# frontend

The web app that displays sensor readings and drought forecasts. Talks to `backend/`'s API — it
doesn't touch the database or LoRa data directly.

This folder is intentionally empty for now (no `package.json` yet). To scaffold it:

```
npm create vite@latest . -- --template react-ts
```

(run from inside `frontend/`, using `.` so Vite scaffolds into this existing folder rather than
creating a new one).

Once scaffolded, `just frontend` will run the Vite dev server.
