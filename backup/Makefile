.PHONY: dev prod down reset seed test lint build help

# ── Dev ────────────────────────────────────────────────────────
dev:
	@echo "Starting PayrollOS dev environment..."
	docker compose up -d postgres redis
	@sleep 3
	docker compose exec -T postgres psql -U payroll -d payrolldb -f /docker-entrypoint-initdb.d/init.sql 2>/dev/null || true
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
	cd frontend && npm start

dev-docker:
	docker compose up --build

# ── DB only ────────────────────────────────────────────────────
db:
	docker compose up -d postgres redis
	@echo "PostgreSQL ready on :5432, Redis on :6379"

db-init:
	docker compose exec postgres psql -U payroll -d payrolldb < database/init.sql

db-reset:
	docker compose down -v
	docker compose up -d postgres redis
	@sleep 3
	$(MAKE) db-init

# ── Seed ───────────────────────────────────────────────────────
seed:
	cd backend && DATABASE_URL=postgresql://payroll:payroll_secret@localhost:5432/payrolldb \
		python3 seed.py

# ── Tests ──────────────────────────────────────────────────────
test:
	cd backend && pytest tests/test_calculator.py tests/test_extended.py -v --tb=short

test-all:
	cd backend && pytest tests/ -v --tb=short

test-cov:
	cd backend && pytest tests/test_calculator.py tests/test_extended.py \
		--cov=services/calculator --cov-report=html --cov-report=term-missing

test-integration:
	@echo "Starting server for integration tests..."
	cd backend && PAYROLLOS_TEST_URL=http://localhost:8000 pytest tests/test_integration.py -v --tb=short

# ── Load test ──────────────────────────────────────────────────
load-test:
	cd backend && locust -f locustfile.py --host=http://localhost:8000 \
		--users=50 --spawn-rate=5 --run-time=60s --headless

load-test-ui:
	cd backend && locust -f locustfile.py --host=http://localhost:8000

# ── Prod ───────────────────────────────────────────────────────
prod:
	docker compose -f docker-compose.prod.yml up -d

prod-build:
	docker compose -f docker-compose.prod.yml build

migrate:
	cd backend && alembic upgrade head

# ── Utils ──────────────────────────────────────────────────────
down:
	docker compose down

reset: down
	docker compose down -v
	$(MAKE) dev-docker

logs:
	docker compose logs -f backend

lint:
	cd backend && python3 -m py_compile main.py && \
		find routes services utils middleware -name "*.py" -exec python3 -m py_compile {} \; && \
		echo "✓ All Python files syntax OK"

check:
	@python3 -c "\
import ast, os; \
ok=[]; errs=[]; \
[([ast.parse(open(os.path.join(r,f)).read()), ok.append(f)] if True else None) \
 if not (lambda p: (ast.parse(open(p).read()), ok.append(os.path.basename(p)))[0])(os.path.join(r,f)) else errs.append(f) \
 for r,d,fs in os.walk('backend') for f in fs if f.endswith('.py') and '__pycache__' not in r]; \
print(f'Backend: {len(ok)} files, {len(errs)} errors')"

# ── Install ────────────────────────────────────────────────────
install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

install-cli:
	pip install click requests tabulate
	chmod +x cli/payrollos
	ln -sf $(PWD)/cli/payrollos /usr/local/bin/payrollos
	@echo "✓ PayrollOS CLI installed. Run: payrollos --help"

# ── Postman + OpenAPI ──────────────────────────────────────────
postman:
	@echo "Download Postman collection: http://localhost:8000/openapi/postman"
	curl -s http://localhost:8000/openapi/postman -H "Authorization: Bearer $$(cat .token 2>/dev/null || echo '')" -o payrollos-postman.json
	@echo "✓ Saved to payrollos-postman.json"

openapi:
	curl -s http://localhost:8000/openapi/spec -o payrollos-openapi.json
	@echo "✓ OpenAPI spec saved to payrollos-openapi.json"

# ── Help ───────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  PayrollOS — Make commands"
	@echo ""
	@echo "  make dev          Start dev (DB in Docker, API + frontend local)"
	@echo "  make dev-docker   Start everything in Docker"
	@echo "  make db           Start only PostgreSQL + Redis"
	@echo "  make db-init      Run init.sql against running DB"
	@echo "  make db-reset     Wipe and reinitialize the database"
	@echo "  make seed         Seed database with 25 test employees"
	@echo "  make test         Run unit tests (fast, no server needed)"
	@echo "  make test-all     Run all tests including integration"
	@echo "  make test-cov     Unit tests with coverage report"
	@echo "  make load-test    Headless load test (50 users, 60s)"
	@echo "  make prod         Start production stack"
	@echo "  make migrate      Run Alembic migrations"
	@echo "  make lint         Syntax check all Python files"
	@echo "  make install      Install all dependencies"
	@echo "  make install-cli  Install payrollos CLI tool"
	@echo "  make postman      Download Postman collection"
	@echo ""
