.PHONY: help run-api run-webhook-receiver run-alert-demo test-alert-demo test-alerting

help:
	@echo "Available targets:"
	@echo "  run-api              Start main FastAPI service on :8000"
	@echo "  run-webhook-receiver Start demo webhook receiver on :9000"
	@echo "  run-alert-demo       Run one-command SLO alert flow demo"
	@echo "  test-alert-demo      Run tests for alert flow demo + webhook security"
	@echo "  test-alerting        Run broader alerting-related test suite"

run-api:
	python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

run-webhook-receiver:
	python -m uvicorn demo.webhook_receiver:app --host 0.0.0.0 --port 9000 --reload

run-alert-demo:
	python demo/run_alert_flow.py --host http://localhost:8000 --receiver http://localhost:9000 --errors 30

test-alert-demo:
	pytest -q tests/test_run_alert_flow_demo.py tests/test_webhook_receiver_demo.py tests/test_webhook_security.py

test-alerting:
	pytest -q tests/test_alerts.py tests/test_api.py tests/test_metrics.py tests/test_webhook_security.py tests/test_webhook_receiver_demo.py tests/test_run_alert_flow_demo.py
