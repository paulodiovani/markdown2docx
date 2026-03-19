.DEFAULT_GOAL := build
.PHONY: clean install lint format

# Use the existing venv
PIP = .venv/bin/pip
PYTHON = .venv/bin/python

DOCX_OUTPUT = markdown2docx
CONFLUENCE_OUTPUT = markdown2confluence
PREFIX = $(HOME)/.local

.venv:
	@echo "Setting up virtual environment..."
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

build: .venv
	@echo "Building standalone executables..."
	$(PIP) install pyinstaller
	$(PYTHON) -m PyInstaller --onefile --name $(DOCX_OUTPUT) $(DOCX_OUTPUT).py
	$(PYTHON) -m PyInstaller --onefile --name $(CONFLUENCE_OUTPUT) $(CONFLUENCE_OUTPUT).py

clean:
	rm -rf build dist *.spec

install: build
	@echo "Installing to $(PREFIX)/bin..."
	@mkdir -p $(PREFIX)/bin
	cp dist/$(DOCX_OUTPUT) $(PREFIX)/bin/
	cp dist/$(CONFLUENCE_OUTPUT) $(PREFIX)/bin/

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .
