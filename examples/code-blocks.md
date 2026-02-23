# Code Blocks

Syntax highlighting showcase for various languages.

## Python

```python
import os
from dataclasses import dataclass, field

# Constants and numbers
MAX_RETRIES = 3
PI = 3.14159

@dataclass
class Config:
    """Application configuration."""
    name: str
    debug: bool = False
    tags: list[str] = field(default_factory=list)

def process(items: list[int]) -> dict[str, int]:
    """Process a list of items and return statistics."""
    if not items:
        raise ValueError("Empty list")
    total = sum(items)
    return {"count": len(items), "total": total, "max": max(items)}

# List comprehension and f-strings
results = [f"item_{i}" for i in range(10) if i % 2 == 0]
print(f"Results: {results!r}")
```

## JavaScript / TypeScript

```javascript
// Arrow functions and template literals
const greet = (name) => `Hello, ${name}!`;

// Async/await with destructuring
async function fetchUser(id) {
  const response = await fetch(`/api/users/${id}`);
  const { name, email, roles = [] } = await response.json();
  return { name, email, isAdmin: roles.includes("admin") };
}

// Classes and symbols
class EventEmitter {
  #listeners = new Map();

  on(event, callback) {
    if (!this.#listeners.has(event)) {
      this.#listeners.set(event, []);
    }
    this.#listeners.get(event).push(callback);
  }

  emit(event, ...args) {
    this.#listeners.get(event)?.forEach((cb) => cb(...args));
  }
}
```

## HTML

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sample Page</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header id="main-header" class="sticky">
    <nav aria-label="Main navigation">
      <a href="/">Home</a>
      <a href="/about">About</a>
    </nav>
  </header>
  <main>
    <p>Hello, <strong>world</strong>!</p>
  </main>
  <script src="app.js" defer></script>
</body>
</html>
```

## CSS

```css
:root {
  --primary: #3b82f6;
  --spacing: 1rem;
}

body {
  font-family: "Inter", sans-serif;
  line-height: 1.6;
  color: #1f2937;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing);
}

@media (max-width: 768px) {
  .container {
    padding: calc(var(--spacing) / 2);
  }
}

button:hover {
  background-color: var(--primary);
  transform: scale(1.05);
  transition: all 0.2s ease-in-out;
}
```

## Bash

```bash
#!/bin/bash
set -euo pipefail

# Variables and string interpolation
APP_NAME="myapp"
VERSION=$(git describe --tags --always)
BUILD_DIR="./build/${APP_NAME}"

echo "Building ${APP_NAME} v${VERSION}..."

# Conditional and loop
if [ -d "$BUILD_DIR" ]; then
    rm -rf "$BUILD_DIR"
fi

mkdir -p "$BUILD_DIR"

for file in src/*.py; do
    cp "$file" "$BUILD_DIR/"
    echo "  Copied: $(basename "$file")"
done

echo "Build complete!"
```

## SQL

```sql
SELECT
    u.name,
    u.email,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total), 0) AS total_spent
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.created_at >= '2024-01-01'
    AND u.status = 'active'
GROUP BY u.id, u.name, u.email
HAVING COUNT(o.id) > 5
ORDER BY total_spent DESC
LIMIT 20;
```

## Rust

```rust
use std::collections::HashMap;

fn word_count(text: &str) -> HashMap<&str, usize> {
    let mut counts: HashMap<&str, usize> = HashMap::new();
    for word in text.split_whitespace() {
        *counts.entry(word).or_insert(0) += 1;
    }
    counts
}

fn main() {
    let text = "hello world hello rust world hello";
    let counts = word_count(text);
    for (word, count) in &counts {
        println!("{word}: {count}");
    }
}
```

## Go

```go
package main

import (
	"fmt"
	"strings"
)

type Result struct {
	Word  string
	Count int
}

func wordCount(text string) []Result {
	counts := make(map[string]int)
	for _, word := range strings.Fields(text) {
		counts[strings.ToLower(word)]++
	}
	results := make([]Result, 0, len(counts))
	for word, count := range counts {
		results = append(results, Result{Word: word, Count: count})
	}
	return results
}

func main() {
	for _, r := range wordCount("Hello World hello Go world") {
		fmt.Printf("%s: %d\n", r.Word, r.Count)
	}
}
```

## No Language Specified

```
This is a plain text code block.
No syntax highlighting is applied here.
It uses the TextLexer fallback.

    Indentation is preserved.
    Special characters: <>&"' are kept as-is.
```
