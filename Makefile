# Build the Docker image
build:
	docker build -t app .

# Run the container (without Docker Compose)
run:
	docker run -p 5000:5000 app

# Run the app with Docker Compose
start:
	docker compose up

# Stop the running services
stop:
	docker compose down

# Restart the app service only
restart:
	docker compose restart app

# Rebuild everything from scratch
rebuild:
	docker compose up --build --force-recreate --remove-orphans -d

# Remove all Docker containers, images, and networks
clean:
	docker system prune -af --volumes

# Restart & rebuild the app container only
refresh:
	docker compose up -d --build app