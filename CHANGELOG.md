# Changelog

## 2026.3.20 (882a0e0)

### Fixed

- Fix internal links in DOCX (bookmark anchors on headings) and Confluence (case-sensitive heading anchors)

## 2026.3.19 (3ba687b)

### Added

- Add `--dry-run` option for Confluence export
- Support mermaid diagram themes

### Fixed

- Update comment reanchoring code to match by context
- Set width for images on page
- Increase image quality for mermaid diagrams

### Changed

- Update name, description and logo

## 2026.2.24 (61cdea5)

### Added

- Add Confluence export (`markdown2confluence`) with ADF format support
  - Create and update Confluence pages from Markdown
  - Support for tables, alerts, images, and code blocks
  - Handle comments anchoring and attachment uploads
  - Configuration via TOML config file
- Add Makefile and installer for both executables

## 2026.2.23 (56f9de1)

### Added

- Create markdown converter using Claude
- Parse and render alert notes
- Add mermaid diagram support via `mmdc`
- Add syntax highlighting for code blocks via Pygments
- Add ruff linter, `.editorconfig`, and GitHub Actions workflow
- Add example files
- Add LICENSE

### Fixed

- Fix image support
- Reduce big diagrams to fit inside a page
- Reduce max height for diagrams
- Fix puppeteer error on CI

### Changed

- Do not catch errors, let exceptions propagate naturally
