"""Modules locked out of the Layer 0 trust boundary.

# why this directory exists: Layer 0 (core agent loop) must be fully
# hardened and trusted before any higher-layer feature is reactivated.
# Moving modules here makes the trust boundary visible in the filesystem.
# The directory name "_unlocked" is intentional — these modules are not
# deleted, they will be graduated back to hal/ layer by layer:
#
#   Layer 1: intent.py          (embedding-based intent routing)
#   Layer 2: agents.py          (Planner/Critic sub-agents)
#   Layer 3: security.py, web.py, trust_metrics.py, postmortem.py,
#            falco_noise.py, watchdog.py
#   Layer 4: server.py, telegram.py
#
# To graduate a module: git mv hal/_unlocked/foo.py hal/foo.py,
# update imports, verify tests, merge to main.
"""
