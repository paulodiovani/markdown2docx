OUTPUT=markdown2docx
PREFIX=$(HOME)/.local/bin

build:
	pip install pyinstaller
	pyinstaller --onefile $(OUTPUT).py

.PHONY: clean
clean:
	rm -rf build dist $(OUTPUT).spec

.PHONY: install
install: build
	cp -v dist/$(OUTPUT) $(PREFIX)
