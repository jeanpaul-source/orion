# Configuration Directory

Search term definitions and profile configurations for the harvester.

## Files

- **`search_terms.csv`** - Main search terms (272 terms across 11 categories)
  - Format: `term,category`
  - Used by unified `orion` CLI for batch harvesting
  - See parent README.md for category descriptions

- **`orion.toml`** - Profile definitions for multi-machine orchestration
  - Profiles: `host` (default, GPU access), `laptop` (CPU-only), `dev` (local services)
  - Defines service URLs, feature flags, hardware capabilities
  - Use with: `orion --profile laptop query "test"`

- **`profiles/`** - Profile-specific configuration overrides
  - Directory for environment-specific settings
