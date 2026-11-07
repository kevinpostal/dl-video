.PHONY: test deploy logs backfill

HOST := ovh
DIR := /opt/bj-files

test:
	mix test

# Sync sources, build on the host (native amd64), restart. The host's .env
# (UPLOAD_TOKEN) and data/ are left alone.
deploy:
	ssh $(HOST) 'sudo mkdir -p $(DIR)/data && sudo chown -R $$USER $(DIR)'
	rsync -az --delete --exclude _build --exclude deps --exclude tmp --exclude data --exclude .env ./ $(HOST):$(DIR)/
	ssh $(HOST) 'cd $(DIR) && test -f .env && sudo docker compose up -d --build'

logs:
	ssh $(HOST) 'sudo docker logs --tail 100 -f bj-files'

# Run inside the live node so backfill shares its bounded admission gate.
# Failed legacy originals are preserved; rerunning skips already-ready files.
backfill:
	ssh $(HOST) 'cd $(DIR) && sudo docker compose exec -T bj-files /app/bin/bj_files rpc "result = BjFiles.Media.backfill(); IO.inspect(result, limit: :infinity); if result.failed != [], do: raise(\"backfill failed for some originals\")"'
