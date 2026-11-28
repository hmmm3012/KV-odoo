# Harness shortcuts for the Odoo 19 custom tree.
# Never point these targets at production (kv-odoo) or Odoo 18 staging.

.PHONY: init verify test upgrade reset-db invariants xpath help

MODULE ?=

help:
	@echo "make init                 # ./init.sh (background health)"
	@echo "make verify MODULE=name   # ./scripts/agent-verify.sh <module>"
	@echo "make test MODULE=name     # alias for verify"
	@echo "make upgrade MODULE=name  # alias for verify (upgrade+tests on a temp DB)"
	@echo "make reset-db             # ensure odoo_19_test_tpl exists"
	@echo "make invariants           # scripts/check-odoo19-invariants.py"
	@echo "make xpath                # xpath_check on the 73-module stack"

init:
	./init.sh

verify:
	@if [ -z "$(MODULE)" ]; then echo "Usage: make verify MODULE=hr_employee_kv"; exit 2; fi
	./scripts/agent-verify.sh $(MODULE)

test: verify

upgrade: verify

reset-db:
	./scripts/agent-reset-testdb.sh --ensure-template

invariants:
	python3 scripts/check-odoo19-invariants.py

xpath:
	./scripts/agent-verify.sh --skip-runtime $(if $(MODULE),$(MODULE),hr_employee_kv)
