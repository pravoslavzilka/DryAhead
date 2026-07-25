# Convenience recipes for local development.
# Fill in the TODOs once each part of the project has real dependencies installed.

# Run the FastAPI backend with auto-reload
backend:
    cd backend && uvicorn app.main:app --reload --app-dir src

# Run the Vite dev server
frontend:
    cd frontend && npm run dev

# Build firmware with PlatformIO
fw-build:
    cd firmware && pio run
