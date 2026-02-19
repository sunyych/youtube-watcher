build:
	docker compose down
	docker compose build
	docker compose up -d

build-ui:
	docker compose stop frontend
	docker compose build frontend
	docker compose up -d frontend

build-backend:
	docker compose stop backend queue postgres
	docker compose build backend queue postgres
	docker compose up -d backend queue postgres