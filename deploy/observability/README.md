# Observability Deployment Assets

This folder contains example provisioning assets for the API-only operator stack:

- `prometheus.yml`: scrape config for `/metrics`
- `alert_rules.yml`: example alert rules
- `grafana/provisioning/`: datasource and dashboard provisioning
- `grafana/dashboards/media-manager-overview.json`: starter dashboard

These files are examples for local development and small deployments. Review
targets, ports, and thresholds before using them in shared environments.
