# Changelog

## v0.9-cli-architecture

<!-- Final stable release that still includes CLI orchestration before the API-only architecture pivot. -->

### Summary

Stable baseline before API-only architecture pivot.

### Features

- Media file ingestion pipeline
- SHA-256 hash calculation
- Duplicate detection and canonical discovery
- Database-backed media tracking
- REST API endpoints for querying media
- CLI orchestration for ingestion and processing workflows

### Architecture

- Hybrid CLI + API workflow
- CLI used to trigger ingestion, hashing, and discovery tasks
- GUI interacts with the REST API for media browsing and querying

### Upcoming Changes

- Removal of CLI orchestration layer
- Transition to API-first architecture
- GUI and tooling will interact exclusively with REST endpoints
