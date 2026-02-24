.PHONY: clean install lint format

# Use the existing venv
PIP = .venv/bin/pip
PYTHON = .venv/bin/python

OUTPUT = markdown2docx
PREFIX = $(HOME)/.local

build:
	@echo "Building standalone executable..."
	$(PIP) install pyinstaller
	$(PYTHON) -m PyInstaller --onefile --name $(OUTPUT) $(OUTPUT).py

clean:
	rm -rf build dist *.spec

install: build
	@echo "Installing to $(PREFIX)/bin..."
	@mkdir -p $(PREFIX)/bin
	cp dist/markdown2docx $(PREFIX)/bin/

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .
