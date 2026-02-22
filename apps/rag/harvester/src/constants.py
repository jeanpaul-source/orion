"""
Constants and configuration for ORION Harvester.

All API endpoints, thresholds, and configuration values.
"""

import os

# API Endpoints
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_API = "http://export.arxiv.org/api/query"
CORE_API = "https://api.core.ac.uk/v3/search/works"
OPENALEX_API = "https://api.openalex.org/works"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
CROSSREF_API = "https://api.crossref.org/works"
ZENODO_API = "https://zenodo.org/api/records"
GITHUB_API = "https://api.github.com"
STACKOVERFLOW_API = "https://api.stackexchange.com/2.3/search/advanced"
DBLP_API = "https://dblp.org/search/publ/api"
BIORXIV_API = "https://api.biorxiv.org/details/biorxiv"
MEDRXIV_API = "https://api.biorxiv.org/details/medrxiv"
PUBMED_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HAL_API = "https://api.archives-ouvertes.fr/search"

# Rate Limiting
RATE_LIMIT_DELAY = 5  # seconds between requests

# Environment-based Configuration
USE_EMBEDDINGS = os.environ.get("ORION_USE_EMBEDDINGS", "false").lower() == "true"
CONTACT_EMAIL = os.environ.get("ORION_CONTACT_EMAIL")
S2_API_KEY = os.environ.get("ORION_S2_API_KEY")
CORE_API_KEY = os.environ.get("ORION_CORE_API_KEY")
GITHUB_TOKEN = os.environ.get("ORION_GITHUB_TOKEN")
SO_API_KEY = os.environ.get("ORION_SO_API_KEY")

# Quality Thresholds
SIMILARITY_THRESHOLD = 0.65  # Minimum cosine similarity for relevance
MIN_GITHUB_STARS = int(os.environ.get("ORION_MIN_GITHUB_STARS", "100"))
MIN_SO_SCORE = int(os.environ.get("ORION_MIN_SO_SCORE", "10"))
MIN_SO_ANSWERS = 1
MAX_RESULTS_PER_TERM = int(os.environ.get("ORION_MAX_RESULTS_PER_TERM", "5"))

# Rate Limit Warnings
SO_RATE_LIMIT_WARNING = """
⚠️  Stack Overflow Rate Limits:
  - Unauthenticated: 300 requests/day
  - With API key: 10,000 requests/day
  - Set ORION_SO_API_KEY environment variable to increase limits
  - Get your key at: https://stackapps.com/apps/oauth/register
"""

GITHUB_RATE_LIMIT_WARNING = """
⚠️  GitHub Rate Limits:
  - Unauthenticated: 60 requests/hour
  - With token: 5,000 requests/hour
  - Set ORION_GITHUB_TOKEN environment variable to increase limits
  - Generate token at: https://github.com/settings/tokens
"""

# Venue Preferences (by category)
VENUE_PREFERENCES = {
    "data-persistence-stores": {
        "proceedings of the vldb endowment", "vldb", "sigmod", "icde",
        "pods", "cidr", "acm transactions on database systems"
    },
    "gpu-passthrough-and-vgpu": {
        "sc", "hpca", "ics", "pact", "pmap", "ieee transactions on parallel",
        "gpu technology conference"
    },
    "llm-serving-and-inference": {
        "neurips", "iclr", "acl", "naacl", "emnlp", "mlsys", "hotchips"
    }
}

LOW_QUALITY_VENUE_KEYWORDS = {
    "international journal of", "international conference on education",
    "international journal of innovative", "journal of emerging",
    "academic research", "scholar publishing group", "springeropen",
    "ceur workshop", "ijcsi", "ijcsm"
}

# Red Flags (checked against title and abstract)
GENERAL_RED_FLAGS = {
    "covid", "pandemic", "vaccine", "vaccination",
    "medical", "medicine", "healthcare", "patient", "disease",
    "pharmaceutical", "drug", "clinical", "biomedical",
    "agriculture", "agricultural", "farming", "crop",
    "galaxy", "cosmology", "astrophysics", "stellar", "quantum dot",
    "higgs", "quark", "neutrino", "particle physics",
    "bioinformatics", "protein", "genome", "dna", "rna",
    "awesome-", "curated list", "link collection",
    "-tutorial", "tutorial:", "guide:", "beginner guide", "getting started guide"
}

# Category Required Terms (core terminology)
CATEGORY_REQUIRED_TERMS = {
    "vector-databases": {
        "vector database", "vector store", "embedding", "similarity search", 
        "nearest neighbor", "ann", "qdrant", "milvus", "weaviate", "faiss", 
        "pgvector", "hnsw", "chromadb", "pinecone"
    },
    "workflow-automation-n8n": {
        "workflow", "automation", "pipeline", "orchestration", "n8n",
        "dag", "task runner", "process automation"
    },
    "homelab-infrastructure": {
        "proxmox", "kvm", "qemu", "zfs", "ceph", "vm", "virtual machine",
        "hypervisor", "virtualization", "backup", "snapshot", "passthrough",
        "storage", "cluster", "ha", "high availability", "lxc", "pve"
    },
    "gpu-passthrough-and-vgpu": {
        "gpu passthrough", "vgpu", "pcie passthrough", "iommu", "vfio",
        "nvidia", "gpu", "multi-instance gpu", "mig", "cuda", "graphics card",
        "passthrough", "vm gpu", "tensor core", "accelerator"
    },
    "llm-serving-and-inference": {
        "vllm", "model serving", "llm inference", "quantization", "gptq", "awq",
        "gguf", "continuous batching", "paged attention", "tensor parallel",
        "model parallel", "sglang", "llama.cpp", "ollama", "triton", "tensorrt",
        "llm", "transformer", "kv cache", "token throughput"
    },
    "rag-and-knowledge-retrieval": {
        "rag", "retrieval augmented", "hybrid search", "vector search",
        "semantic search", "bm25", "context retrieval", "document retrieval",
        "citation", "grounding", "knowledge base", "embedding", "reranking",
        "query expansion", "relevance scoring"
    },
    "observability-and-alerting": {
        "prometheus", "grafana", "loki", "alerting", "alert", "monitoring",
        "metrics", "observability", "telemetry", "tracing", "logging",
        "time series", "exporter", "dashboard"
    },
    "self-healing-and-remediation": {
        "self-healing", "remediation", "auto-remediation", "chaos engineering",
        "fault tolerance", "resilience", "incident response", "runbook",
        "playbook", "sre", "recovery", "rollback", "circuit breaker", "failover"
    },
    "homelab-networking-security": {
        "proxmox network", "vlan", "firewall", "vpn", "wireguard", "openvpn",
        "network segmentation", "bridge", "routing", "iptables", "nftables",
        "pve-firewall", "certificate", "tls", "secrets management"
    },
    "container-platforms": {
        "docker", "kubernetes", "k8s", "k3s", "container", "containerd",
        "docker compose", "swarm", "pod", "deployment", "helm", "service mesh"
    },
    "data-persistence-stores": {
        "qdrant", "vector database", "postgresql", "postgres", "time series",
        "victoriametrics", "influxdb", "metadata store", "persistence",
        "database deployment", "backup strategy", "replication"
    }
}

# Secondary synonyms for softer acceptance
CATEGORY_SECONDARY_TERMS = {
    "vector-databases": {
        "semantic search", "vector store", "retrieval", "approximate search",
        "distance metric", "cosine similarity", "hnsw", "ann"
    },
    "homelab-infrastructure": {
        "pve", "proxmox ve", "lxc", "container", "pve-firewall", "pveceph",
        "replication", "migration", "resource allocation", "storage pool",
        "bare metal", "cluster"
    },
    "gpu-passthrough-and-vgpu": {
        "nvidia driver", "cuda toolkit", "gpu isolation", "pci device",
        "kernel module", "vfio-pci", "gpu scheduling", "compute capability"
    },
    "llm-serving-and-inference": {
        "openai api", "model loading", "inference optimization", "batch size",
        "context length", "throughput", "latency", "deployment", "api server",
        "serve", "inference engine", "onnx", "batching"
    },
    "rag-and-knowledge-retrieval": {
        "chunk size", "overlap", "reranking", "query expansion", "context window",
        "relevance scoring", "retrieval strategy", "indexing", "document store"
    },
    "observability-and-alerting": {
        "alert rules", "scrape config", "federation", "remote write",
        "log aggregation", "distributed tracing", "slo", "sli", "error budget"
    },
    "self-healing-and-remediation": {
        "auto-scaling", "health check", "failure detection", "retry logic",
        "graceful degradation", "bulkhead pattern", "timeout", "rate limiting"
    },
    "homelab-networking-security": {
        "subnet", "dhcp", "dns", "port forwarding", "nat", "gateway",
        "security group", "access control", "ssh", "authentication"
    },
    "container-platforms": {
        "dockerfile", "image", "registry", "orchestration", "ingress",
        "service discovery", "volume", "networking", "resource limits",
        "service mesh", "istio", "helm", "scheduler"
    },
    "data-persistence-stores": {
        "replication", "sharding", "indexing", "query performance",
        "connection pooling", "wal", "checkpoint", "vacuum", "oltp", "olap"
    },
    "workflow-automation-n8n": {
        "workflow engine", "task scheduling", "dag execution", "webhook",
        "integration", "automation tool"
    }
}

# Category-specific exclusions
CATEGORY_EXCLUSION_TERMS = {
    "data-persistence-stores": {"drug", "disease", "medical", "healthcare", "education"},
    "rag-and-knowledge-retrieval": {"drug", "clinical", "education"},
    "workflow-automation-n8n": {"education", "curriculum"}
}

# Stack Overflow tags mapped to categories (for filtering)
SO_CATEGORY_TAGS = {
    "vector-databases": ["vector", "similarity-search", "elasticsearch", "machine-learning", "qdrant"],
    "workflow-automation-n8n": ["automation", "workflow", "orchestration", "n8n", "airflow"],
    "homelab-infrastructure": ["proxmox", "kvm", "qemu", "virtualization", "zfs", "ceph", "homelab"],
    "gpu-passthrough-and-vgpu": ["gpu", "pci-passthrough", "vfio", "iommu", "nvidia", "virtualization", "cuda"],
    "llm-serving-and-inference": ["machine-learning", "model-deployment", "inference", "pytorch", "tensorflow", "llm"],
    "rag-and-knowledge-retrieval": ["information-retrieval", "search", "nlp", "machine-learning", "embeddings", "rag"],
    "observability-and-alerting": ["prometheus", "grafana", "monitoring", "alerting", "metrics", "logging"],
    "self-healing-and-remediation": ["devops", "sre", "automation", "high-availability", "fault-tolerance"],
    "homelab-networking-security": ["networking", "firewall", "vpn", "security", "ssl", "linux", "proxmox"],
    "container-platforms": ["docker", "kubernetes", "containers", "orchestration", "deployment"],
    "data-persistence-stores": ["postgresql", "database", "time-series", "monitoring", "performance"]
}

# Allow-listed domains for official documentation
OFFICIAL_DOCS_DOMAINS = {
    "kubernetes.io", "k8s.io",
    "postgresql.org", "www.postgresql.org",
    "docs.nvidia.com", "nvidia.com",
    "docker.com", "docs.docker.com",
    "prometheus.io",
    "grafana.com",
    "redis.io",
    "mongodb.com",
    "qdrant.tech",
    "weaviate.io",
    "milvus.io",
    "python.org", "docs.python.org",
    "pytorch.org",
    "tensorflow.org"
}

# Reputable tech blog RSS feeds
TECH_BLOG_FEEDS = {
    "https://engineering.fb.com/feed/": "Meta Engineering",
    "https://aws.amazon.com/blogs/aws/feed/": "AWS Blog",
    "https://netflixtechblog.com/feed": "Netflix Tech Blog",
    "https://github.blog/feed/": "GitHub Blog",
    "https://stackoverflow.blog/feed/": "Stack Overflow Blog",
}

__all__ = [
    "SEMANTIC_SCHOLAR_API",
    "ARXIV_API",
    "CORE_API",
    "OPENALEX_API",
    "UNPAYWALL_API",
    "CROSSREF_API",
    "ZENODO_API",
    "DBLP_API",
    "BIORXIV_API",
    "MEDRXIV_API",
    "PUBMED_API",
    "HAL_API",
    "GITHUB_API",
    "STACKOVERFLOW_API",
    "RATE_LIMIT_DELAY",
    "USE_EMBEDDINGS",
    "CONTACT_EMAIL",
    "S2_API_KEY",
    "CORE_API_KEY",
    "GITHUB_TOKEN",
    "SO_API_KEY",
    "SIMILARITY_THRESHOLD",
    "MIN_GITHUB_STARS",
    "MIN_SO_SCORE",
    "MIN_SO_ANSWERS",
    "MAX_RESULTS_PER_TERM",
    "SO_RATE_LIMIT_WARNING",
    "GITHUB_RATE_LIMIT_WARNING",
    "VENUE_PREFERENCES",
    "LOW_QUALITY_VENUE_KEYWORDS",
    "GENERAL_RED_FLAGS",
    "CATEGORY_REQUIRED_TERMS",
    "CATEGORY_SECONDARY_TERMS",
    "CATEGORY_EXCLUSION_TERMS",
    "SO_CATEGORY_TAGS",
    "OFFICIAL_DOCS_DOMAINS",
    "TECH_BLOG_FEEDS",
]
