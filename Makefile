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

build-queue:
	docker compose stop queue
	docker compose build queue
	docker compose up -d queue

# --- Maintenance: run with docker (ensure postgres + backend image available) ---
# Refresh titles for records that have no title (yt-dlp metadata only; member-only -> marked unavailable).
refresh-titles:
	docker compose run --rm backend python -m app.scripts.refresh_titles

# Re-queue completed videos without transcript (or "Transcription unavailable") for re-transcription.
re-transcribe:
	docker compose run --rm backend python -m app.scripts.re_transcribe

# Re-queue completed videos without summary for re-summarization.
re-summarize:
	docker compose run --rm backend python -m app.scripts.re_summarize

# Mark failed videos whose error is member-only as unavailable (excluded from failed list).
mark-membership-unavailable:
	docker compose run --rm backend python -m app.scripts.mark_membership_unavailable