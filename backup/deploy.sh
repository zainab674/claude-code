#!/bin/bash
# ================================================================
# PayrollOS Deployment Script
# Day 3: Deploy backend to DigitalOcean, frontend to Vercel
# ================================================================
set -e

echo "=== PayrollOS Deploy ==="

# ── Option A: Deploy everything with Docker Compose (VPS) ───────
deploy_vps() {
  echo "→ Deploying to VPS with Docker Compose..."
  
  # Copy files to server
  rsync -avz --exclude=node_modules --exclude=__pycache__ \
    ./ user@your-server-ip:/opt/payrollos/

  ssh user@your-server-ip << 'ENDSSH'
    cd /opt/payrollos
    
    # Pull latest images
    docker compose pull
    
    # Run DB migrations
    docker compose run --rm backend alembic upgrade head
    
    # Start/restart services
    docker compose up -d --build
    
    # Health check
    sleep 5
    curl -f http://localhost:8000/health || echo "Backend not ready yet"
    
    echo "✓ Deployed successfully"
ENDSSH
}

# ── Option B: DigitalOcean App Platform ─────────────────────────
deploy_do() {
  echo "→ Deploying to DigitalOcean App Platform..."
  
  # Install doctl: https://docs.digitalocean.com/reference/doctl/
  # doctl auth init
  
  doctl apps create --spec .do/app.yaml
  # Or update existing:
  # doctl apps update $APP_ID --spec .do/app.yaml
}

# ── Option C: AWS ECS (Fargate) ──────────────────────────────────
deploy_aws() {
  echo "→ Deploying to AWS ECS..."
  
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  REGION=${AWS_REGION:-us-east-1}
  
  # Build and push to ECR
  aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
  
  docker build -t payrollos-api ./backend
  docker tag payrollos-api:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/payrollos-api:latest
  docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/payrollos-api:latest
  
  # Update ECS service
  aws ecs update-service --cluster payrollos --service payrollos-api --force-new-deployment
  
  echo "✓ ECS deployment triggered"
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
  docker compose up -d postgres
  
  echo "  Waiting for PostgreSQL..."
  until docker compose exec postgres pg_isready -U payroll -d payrolldb; do
    sleep 1
  done
  
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
  
  trap "kill $BACKEND_PID $FRONTEND_PID; docker compose stop" EXIT
  wait
}

# ── Parse command ────────────────────────────────────────────────
case "${1:-dev}" in
  dev)       dev_start ;;
  vps)       deploy_vps ;;
  do)        deploy_do ;;
  aws)       deploy_aws ;;
  frontend)  deploy_frontend ;;
  migrate)   run_migrations ;;
  *)
    echo "Usage: $0 [dev|vps|do|aws|frontend|migrate]"
    echo ""
    echo "  dev       Start local dev environment (default)"
    echo "  vps       Deploy to VPS via rsync + Docker Compose"
    echo "  do        Deploy to DigitalOcean App Platform"
    echo "  aws       Deploy backend to AWS ECS"
    echo "  frontend  Deploy frontend to Vercel"
    echo "  migrate   Run Alembic DB migrations"
    ;;
esac
