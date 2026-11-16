PYTHON ?= python
TASKS = bootstrap install-tools build-test dev-up db-up db-down migrate check test-unit test-integration test-draw test-privacy test-e2e check-accessibility check-security qualify build-prod check-prod-artifact backup-drill verify-release
.PHONY: $(TASKS)
$(TASKS):
	$(PYTHON) scripts/tasks.py $@
