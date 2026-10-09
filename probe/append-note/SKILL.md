---
name: append-note
description: Use when the user pastes a short post and asks to save it to notes. Appends it to notes.md as a numbered entry. Do not use for questions about code.
---
1. Run Grep for `## POST` in `notes.md` to find the highest number n (0 if none).
2. Append to `notes.md`: a line `## POST n+1 — "<first line of the text>"`, an empty line, the text verbatim.
