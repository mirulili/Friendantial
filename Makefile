# Makefile for Friendantial Project

# Docker-related variables
IMAGE_NAME := friendantial-app
TAG := latest
CONTAINER_NAME := friendantial

.PHONY: all build up down logs shell clean help

all: build up

# Build the Docker image
build:
	@echo "Building Docker image: $(IMAGE_NAME):$(TAG)..."
	docker build -t $(IMAGE_NAME):$(TAG) .

# Start the service using Docker Compose
up:
	@echo "Starting service..."
	docker-compose up -d

# Stop and remove the service containers
down:
	@echo "Stopping service..."
	docker-compose down

# View logs of the running service
logs:
	@echo "Showing logs..."
	docker-compose logs -f

# Access the running container's shell
shell:
	@echo "Accessing container shell..."
	docker exec -it $(CONTAINER_NAME) /bin/bash

# Remove the Docker image
clean: down
	@echo "Removing Docker image: $(IMAGE_NAME):$(TAG)..."
	docker rmi $(IMAGE_NAME):$(TAG)

help:
	@echo "Available commands:"
	@echo "  make build   - Build the Docker image"
	@echo "  make up      - Start the services in detached mode"
	@echo "  make down    - Stop and remove the services"
	@echo "  make logs    - Follow the logs of the services"
	@echo "  make shell   - Access the running app container's shell"
	@echo "  make clean   - Stop services and remove the Docker image"
	@echo "  make all     - Build and start the services"