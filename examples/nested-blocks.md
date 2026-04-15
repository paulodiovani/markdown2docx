# Nested Blocks Inside Lists

This file exercises block-level content nested inside list items: tables, code
blocks, images, mermaid diagrams, alerts and blockquotes. Ordered list
numbering should remain continuous across any blocks emitted at document
level.

## Table inside ordered list

1. First item
2. Second item with a table below

   | Foo | Bar |
   | --- | --- |
   | foo | bar |

3. Third item after the table
4. Fourth item

## Code block inside ordered list

1. Run this command

   ```bash
   echo hello
   ```

2. Check the output

## Image inside unordered list

- Before the image
- Item with an image

  ![cat](cat.jpg)

- After the image

## Mermaid diagram inside ordered list

1. Define the flow
2. See the diagram below

   ```mermaid
   graph LR
     A[Start] --> B[Middle]
     B --> C[End]
   ```

3. Implement it

## Alert inside ordered list

1. Read carefully

   > [!WARNING]
   > Don't skip this step.

2. Proceed with the next step

## Blockquote inside ordered list

1. As someone once said

   > A quote inside a list item.

2. End of list

## Mixed blocks in a single list

1. Setup

   ```python
   x = 1
   ```

2. Reference table

   | Key | Value |
   | --- | --- |
   | a   | 1     |

3. Done
