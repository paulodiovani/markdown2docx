.DEFAULT_GOAL := build
.PHONY: clean install uninstall lint format test test-unit test-e2e

# Use the existing venv
PIP = .venv/bin/pip
PYTHON = .venv/bin/python

DOCX_OUTPUT = markdown2docx
CONFLUENCE_OUTPUT = markdown2confluence
PREFIX = $(HOME)/.local

# Packages that live in the dev venv but must never be bundled by PyInstaller.
PYINSTALLER_EXCLUDES = \
	--exclude-module pytest \
	--exclude-module _pytest \
	--exclude-module responses \
	--exclude-module ruff \
	--exclude-module coverage

.venv:
	@echo "Setting up virtual environment..."
	python3 -m venv .venv
	$(PIP) install -r requirements-dev.txt

build: .venv
	@echo "Building standalone executables..."
	$(PIP) install pyinstaller pyinstaller-hooks-contrib --upgrade
	$(PYTHON) -m PyInstaller --onefile --name $(DOCX_OUTPUT) $(PYINSTALLER_EXCLUDES) $(DOCX_OUTPUT).py
	$(PYTHON) -m PyInstaller --onefile --name $(CONFLUENCE_OUTPUT) $(PYINSTALLER_EXCLUDES) $(CONFLUENCE_OUTPUT).py

clean:
	rm -rf build dist *.spec

install: build
	@echo "Installing to $(PREFIX)/bin..."
	@mkdir -p $(PREFIX)/bin
	cp dist/$(DOCX_OUTPUT) $(PREFIX)/bin/
	cp dist/$(CONFLUENCE_OUTPUT) $(PREFIX)/bin/

uninstall:
	@echo "Removing from $(PREFIX)/bin..."
	rm -f $(PREFIX)/bin/$(DOCX_OUTPUT)
	rm -f $(PREFIX)/bin/$(CONFLUENCE_OUTPUT)

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .

test: .venv
	$(PYTHON) -m pytest tests/ -v --cov=lib --cov=markdown2docx --cov=markdown2confluence --cov-report=term-missing

test-unit: .venv
	$(PYTHON) -m pytest tests/unit -v

test-e2e: .venv
	$(PYTHON) -m pytest tests/e2e -v
