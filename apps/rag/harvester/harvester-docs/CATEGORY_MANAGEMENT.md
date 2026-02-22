# Category Management Guide

## Overview
Categories are now centrally managed in `VALID_CATEGORIES` with easy CLI tools for adding/removing/renaming.

## Quick Reference

### List all categories
```bash
python3 manage_categories.py list
```

### Add a new category
```bash
python3 manage_categories.py add my-new-category
```

### Remove a category
```bash
python3 manage_categories.py remove old-category
```

### Rename a category
```bash
python3 manage_categories.py rename old-name new-name
```

## Adding a New Category (Full Workflow)

### 1. Add to VALID_CATEGORIES
```bash
python3 manage_categories.py add container-orchestration
```

### 2. Add required filter terms (edit `orion_harvester.py` line ~155)
```python
CATEGORY_REQUIRED_TERMS = {
    # ... existing categories ...
    "container-orchestration": {
        "kubernetes", "k8s", "docker", "container", "pod", "deployment",
        "orchestration", "helm", "service mesh", "istio"
    },
}
```

### 3. Add secondary terms (line ~195)
```python
CATEGORY_SECONDARY_TERMS = {
    # ... existing categories ...
    "container-orchestration": {
        "kubectl", "cluster", "ingress", "daemonset", "statefulset",
        "kube-proxy", "containerd", "cri-o"
    },
}
```

### 4. Add Stack Overflow tags (line ~225)
```python
SO_CATEGORY_TAGS = {
    # ... existing categories ...
    "container-orchestration": [
        "kubernetes", "docker", "containers", "helm", "kubectl"
    ],
}
```

### 5. Add search terms to `search_terms.csv`
```csv
Kubernetes pod scheduling,container-orchestration
Docker Swarm vs Kubernetes,container-orchestration
Helm chart best practices,container-orchestration
```

### 6. Test it
```bash
python3 orion_harvester.py --term "Kubernetes pod scheduling" \
  --category container-orchestration --dry-run --diagnostics
```

## Splitting an Existing Category

### Example: Split infrastructure-and-virtualization

**Step 1: Add new category**
```bash
python3 manage_categories.py add container-orchestration
```

**Step 2: Add filter terms** (as shown above)

**Step 3: Update search_terms.csv**
```bash
# Change container-related terms from infrastructure-and-virtualization 
# to container-orchestration
sed -i 's/,infrastructure-and-virtualization$/,container-orchestration/' \
  search_terms.csv  # (be selective!)
```

**Step 4: New harvests populate new category automatically**
- Existing docs stay in old category (no disruption)
- New harvests flow to correct category
- Optionally migrate old docs later if needed

## Category Naming Rules
- **Lowercase only**: `my-category` ✅ not `My-Category` ❌
- **Hyphens only**: `multi-agent-systems` ✅ not `multi_agent_systems` ❌
- **Descriptive**: `container-orchestration` ✅ not `containers` ❌
- **Consistent**: Match directory names in `data/library/`

## What Gets Updated Automatically

When you use `manage_categories.py`:
- ✅ `VALID_CATEGORIES` set (automatic)
- ✅ Category validation in harvester (automatic)
- ✅ Directory creation (automatic on first harvest)

## What You Must Update Manually

After adding a category:
- ⚠️ `CATEGORY_REQUIRED_TERMS` - Core filter terms
- ⚠️ `CATEGORY_SECONDARY_TERMS` - Supporting terms
- ⚠️ `SO_CATEGORY_TAGS` - Stack Overflow tags
- ⚠️ `search_terms.csv` - Search terms for harvest
- ⚠️ (Optional) `VENUE_PREFERENCES` - Academic venue keywords

## Validation

The harvester now validates categories:
```bash
# This will fail with clear error message:
python3 orion_harvester.py --term "test" --category "invalid" --dry-run

# Output:
# ❌ Invalid category 'invalid'. Valid categories: [...]
```

## Best Practices

1. **Plan first**: List related search terms before adding category
2. **Start small**: Add 5-10 search terms initially, expand later
3. **Test thoroughly**: Use `--dry-run --diagnostics` extensively
4. **Document**: Add comments in `orion_harvester.py` explaining category scope
5. **Gradual migration**: Don't move existing docs unless necessary

## Example: Splitting Infrastructure

Current problem: `infrastructure-and-virtualization` mixes hypervisors + containers (86 docs)

**Solution: Create `container-orchestration` category**

```bash
# 1. Add category
python3 manage_categories.py add container-orchestration

# 2. Edit orion_harvester.py - add filter terms
CATEGORY_REQUIRED_TERMS = {
    "container-orchestration": {
        "kubernetes", "k8s", "docker", "container", "orchestration",
        "helm", "pod", "deployment", "service mesh"
    },
}

# 3. Update search_terms.csv - move K8s/Docker terms
grep "kubernetes\|docker\|helm\|k3s" search_terms.csv | \
  sed 's/infrastructure-and-virtualization/container-orchestration/'

# 4. Next harvest naturally populates new category!
```

**Result:**
- Old docs: Stay in `infrastructure-and-virtualization` (stable)
- New K8s/Docker docs: Go to `container-orchestration` (clean separation)
- Can migrate old docs later if desired

## Troubleshooting

**"Category not found"**
- Run `python3 manage_categories.py list` to see valid categories
- Check spelling and use hyphens (not underscores)

**"Category already exists"**
- Category might be in VALID_CATEGORIES already
- Use `rename` if you want to change it

**Harvest accepts docs in wrong category**
- Check `CATEGORY_REQUIRED_TERMS` - needs relevant keywords
- Use `--diagnostics` to see which terms matched
- Add `CATEGORY_EXCLUSION_TERMS` if needed

**Search terms rejected**
- Verify term has `category` column matching `VALID_CATEGORIES`
- Run validation: `python3 orion_harvester.py` (reads CSV on startup)
