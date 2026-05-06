# Neraium 1.0

Neraium is a customer-facing infrastructure intelligence application for identifying and explaining system-level change in physical operations.

This repository contains the production application for pilot customers.

## Product Principle

Neraium's core intelligence is the infrastructure intelligence engine.

Customer-facing AI features are explanation and workflow layers. They explain Neraium output, evidence, and recommended operator checks. They do not replace or override the core engine.

## Repository Structure

backend/    API, services, engine integration, customer-facing endpoints
frontend/   Customer-facing web application
docs/       Architecture and implementation notes
scripts/    Developer and deployment scripts
tests/      Backend and integration tests
