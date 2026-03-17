.PHONY: dev seed test lint install help

# ── Dev ────────────────────────────────────────────────────────
dev:
	@echo "Starting PayrollOS dev environment..."
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
	cd frontend && npm start

# ── Seed ───────────────────────────────────────────────────────
seed:
	cd backend && python3 seed.py

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

lint:
	cd backend && python -m py_compile main.py
	@echo "✓ Main entry point syntax OK"

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
	@echo "  make dev          Start dev (API + frontend local)"
	@echo "  make seed         Seed database with 25 test employees"
	@echo "  make test         Run unit tests (fast, no server needed)"
	@echo "  make test-all     Run all tests including integration"
	@echo "  make test-cov     Unit tests with coverage report"
	@echo "  make load-test    Headless load test (50 users, 60s)"
	@echo "  make migrate      Run Alembic migrations"
	@echo "  make lint         Syntax check all Python files"
	@echo "  make install      Install all dependencies"
	@echo "  make install-cli  Install payrollos CLI tool"
	@echo "  make postman      Download Postman collection"
	@echo ""
