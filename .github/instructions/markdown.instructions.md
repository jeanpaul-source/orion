# Markdown instructions

These rules apply when editing any `.md` file. The project uses markdownlint-cli2
(config: `.markdownlint-cli2.yaml`). Pre-commit hooks reject violations, so
every markdown edit must be lint-clean before committing.

## Rules that commonly trip up AI assistants

1. **Blank line before and after every list** (MD032). A list must have an empty
   line above its first item and below its last item. This includes
   lists that follow a paragraph or a code fence.

2. **Blank line before and after every fenced code block** (MD031). ` ``` ` must
   have an empty line above and below it, even inside list items.

3. **Ordered list numbering restarts at 1** (MD029). After any interruption
   (heading, prose paragraph, code block), the next ordered list starts at `1.`.
   Do NOT continue numbering from the previous list. Within a single
   uninterrupted list, use sequential numbers: `1.`, `2.`, `3.`.

4. **No inline HTML** is disabled (MD033 = false), but avoid it anyway.

5. **Line length** is unlimited (MD013 = false), but keep lines reasonable.

## Quick self-check

Before committing markdown changes, mentally verify:

- Every list has a blank line above and below it.
- Every code fence (` ``` `) has a blank line above and below it.
- Ordered lists start at 1 after any break.
