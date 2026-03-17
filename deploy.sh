#!/bin/bash
# ================================================================
# PayrollOS Deployment Script
# Day 3: Deploy backend to DigitalOcean, frontend to Vercel
# ================================================================
set -e

echo "=== PayrollOS Deploy ==="

# ── Option A: DigitalOcean App Platform ─────────────────────────
deploy_do() {
  echo "→ Deploying to DigitalOcean App Platform..."
  
  # Install doctl: https://docs.digitalocean.com/reference/doctl/
  # doctl auth init
  
  doctl apps create --spec .do/app.yaml
  # Or update existing:
  # doctl apps update $APP_ID --spec .do/app.yaml
}

# ── Frontend: Vercel ─────────────────────────────────────────────
deploy_frontend() {
  echo "→ Deploying frontend to Vercel..."
  
  cd frontend
  
  # Install Vercel CLI if not present
  which vercel || npm install -g vercel
  
  # Set environment variables
  vercel env add REACT_APP_API_URL production << 'EOF'
https://api.your-domain.com
EOF
  
  # Deploy
  vercel --prod
  
  echo "✓ Frontend deployed to Vercel"
}

# ── Run migrations manually ──────────────────────────────────────
run_migrations() {
  echo "→ Running database migrations..."
  cd backend
  alembic upgrade head
  echo "✓ Migrations complete"
}

# ── Local dev startup ────────────────────────────────────────────
dev_start() {
  echo "→ Starting local development environment..."
  
  echo "  Starting backend..."
  cd backend
  pip install -r requirements.txt -q
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  
  echo "  Starting frontend..."
  cd ../frontend
  npm install -q
  npm start &
  FRONTEND_PID=$!
  
  echo ""
  echo "✓ PayrollOS running:"
  echo "  Frontend: http://localhost:3000"
  echo "  Backend:  http://localhost:8000"
  echo "  API docs: http://localhost:8000/docs"
  echo "  Login:    admin@acme.com / Admin123!"
  echo ""
  echo "  Press Ctrl+C to stop"
  
  trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
  wait
}

# ── Parse command ────────────────────────────────────────────────
case "${1:-dev}" in
  dev)       dev_start ;;
  do)        deploy_do ;;
  frontend)  deploy_frontend ;;
  migrate)   run_migrations ;;
  *)
    echo "Usage: $0 [dev|do|frontend|migrate]"
    echo ""
    echo "  dev       Start local dev environment (default)"
    echo "  vps       Deploy to VPS via rsync + Docker Compose"
    echo "  do        Deploy to DigitalOcean App Platform"
    echo "  aws       Deploy backend to AWS ECS"
    echo "  frontend  Deploy frontend to Vercel"
    echo "  migrate   Run Alembic DB migrations"
    ;;
esac
