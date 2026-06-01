.PHONY: dev backend frontend help

help:
	@echo "Available targets:"
	@echo "  make dev       - Start both backend and frontend"
	@echo "  make backend   - Start backend only (FastAPI + uvicorn)"
	@echo "  make frontend  - Start frontend only (Vite dev server)"

dev:
	python3 scripts/dev.py

backend:
	cd aieng-ui/backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend:
	cd aieng-ui/frontend && npm install && npm run dev
