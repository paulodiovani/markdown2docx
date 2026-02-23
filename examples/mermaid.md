# Mermaid Diagrams

Mermaid diagrams are rendered to PNG via `mmdc` (Mermaid CLI) during conversion.

> [!NOTE]
> The `mmdc` command must be installed for diagrams to render.
> Install it with `npm install -g @mermaid-js/mermaid-cli`.

## Flowchart

```mermaid
flowchart TD
    A[Start] --> B{Is input valid?}
    B -->|Yes| C[Parse Markdown]
    B -->|No| D[Show error]
    C --> E[Generate DOCX]
    E --> F[Save file]
    D --> G[Exit]
    F --> G
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Parser
    participant Renderer

    User->>CLI: markdown2docx input.md
    CLI->>Parser: Parse Markdown to AST
    Parser-->>CLI: Token list
    CLI->>Renderer: Render tokens to DOCX
    Renderer-->>CLI: Document object
    CLI->>User: Save output.docx
```
