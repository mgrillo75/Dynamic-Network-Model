.PHONY: setup test summary ui scenario

setup:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

summary:
	python -m voltagrid_tx3.cli summary

scenario:
	python -m voltagrid_tx3.cli scenario irm_shortfall

ui:
	streamlit run voltagrid_tx3/ui/app.py
