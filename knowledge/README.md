# Ground Truth Knowledge

Files in this directory are the highest-priority source of truth for HAL.
They are version-controlled, travel with `git push`/`git pull`, and are
ingested into pgvector with `doc_tier='ground-truth'`.

## Conventions

- Write in Markdown (`.md`)
- One file per topic (e.g., `LAB_ENVIRONMENT.md`, `NETWORK.md`, `GOALS.md`)
- Keep content factual and current — this is what HAL trusts most
- Update these files when the lab changes
- Do NOT put secrets here — this is git-tracked
