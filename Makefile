rebuild:
	docker compose down
	docker compose build
	docker compose up -d

rebuild-frontend:
	docker compose down
	docker compose build frontend
	docker compose up -d frontend

rebuild-backend:
	docker compose down
	docker compose build backend
	docker compose up -d backend