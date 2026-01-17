# SharePoint RAG Importer - Makefile
# ===================================

.PHONY: help setup up down logs test clean

# Default target
help:
	@echo "SharePoint RAG Importer"
	@echo "======================="
	@echo ""
	@echo "Commands:"
	@echo "  make setup    - Initial setup (copy .env, build images)"
	@echo "  make up       - Start all services"
	@echo "  make down     - Stop all services"
	@echo "  make logs     - View logs"
	@echo "  make test     - Run tests"
	@echo "  make clean    - Remove all data and images"
	@echo ""
	@echo "API Endpoints (after 'make up'):"
	@echo "  http://localhost:8000        - API"
	@echo "  http://localhost:8000/docs   - Swagger UI"
	@echo "  http://localhost:8080        - Adminer (DB UI)"
	@echo "  http://localhost:6333        - Qdrant Dashboard"

# Initial setup
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
		echo "Please edit .env with your credentials"; \
	fi
	docker-compose build

# Start services
up:
	docker-compose up -d
	@echo ""
	@echo "Services starting..."
	@echo "API will be available at http://localhost:8000"
	@echo "Swagger docs at http://localhost:8000/docs"
	@echo ""
	@echo "Wait a few seconds for services to initialize"

# Stop services
down:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# View specific service logs
logs-api:
	docker-compose logs -f api

logs-worker:
	docker-compose logs -f worker

# Run tests
test:
	docker-compose exec api pytest tests/ -v

# Clean everything
clean:
	docker-compose down -v --rmi all
	rm -rf __pycache__ .pytest_cache

# Development - rebuild and restart
dev:
	docker-compose down
	docker-compose build api worker
	docker-compose up -d
	docker-compose logs -f api worker

# Quick test - create connection and import
quicktest:
	@echo "Creating test connection..."
	curl -X POST http://localhost:8000/api/connections \
		-H "Content-Type: application/json" \
		-d '{"name":"Test","tenant_id":"$(TENANT_ID)","client_id":"$(CLIENT_ID)","client_secret":"$(CLIENT_SECRET)"}'

# Database shell
db-shell:
	docker-compose exec postgres psql -U raguser -d ragdb

# Redis shell
redis-shell:
	docker-compose exec redis redis-cli
