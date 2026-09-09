.PHONY: setup test lint api app

PYTHON ?= .venv/Scripts/python.exe

setup:
	$(PYTHON) -m pip install -e .
	$(PYTHON) -m pip install pytest ruff

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check . --exclude .venv

api:
	$(PYTHON) -m uvicorn smelens.api.main:app --reload --port 8000

app:
	$(PYTHON) -m streamlit run smelens/app/workbench.py
