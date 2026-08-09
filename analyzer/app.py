from flask import Flask, request, jsonify
from typing import List, Dict, Any, Tuple, Optional, Set
import zipfile
import os
import tempfile
import re
import json
from urllib.parse import urlparse

app = Flask(__name__)

# =========================================================
# ZEROPS AUTOPILOT - STATIC ARCHITECTURE ANALYZER
# Enterprise Edition - Deterministic Static Analysis
# =========================================================

VERSION = "6.0-Enterprise"

IGNORED_DIRECTORIES: Set[str] = {
    "node_modules", ".git", ".next", "dist", "build",
    "__pycache__", ".venv", "venv", "coverage",
    ".pytest_cache", ".idea", ".vscode", ".turbo",
    ".cache", ".parcel-cache", "target", "vendor"
}

FRONTEND_NAMES: Set[str] = {
    "frontend", "client", "web", "ui", "frontend-app",
    "website", "dashboard", "portal"
}

BACKEND_NAMES: Set[str] = {
    "backend", "server", "api", "service", "backend-api",
    "services", "app-server"
}

WORKER_NAMES: Set[str] = {
    "worker", "workers", "job", "jobs", "queue", "queues",
    "notification", "notifications", "processor", "processing",
    "task", "tasks", "consumer", "consumers", "scheduler",
    "cron", "worker-service"
}

SOURCE_EXTENSIONS: Tuple[str, ...] = (
    ".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs",
    ".rb", ".php", ".cs", ".json", ".yml", ".yaml", ".toml",
    ".env", ".txt", ".properties", ".ini", ".xml"
)

CODE_EXTENSIONS: Tuple[str, ...] = (
    ".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs",
    ".rb", ".php", ".cs"
)

HEALTH_ROUTE_PATTERN = re.compile(
    r'["\'](/(?:api/)?(?:health|healthz|ready|readiness|live|liveness))["\']',
    flags=re.IGNORECASE
)

PORT_PATTERNS: List[str] = [
    r"\bPORT\s*=\s*[\"']?(\d{2,5})",
    r"\bport\s*[:=]\s*[\"']?(\d{2,5})",
    r"\blisten\s*\(\s*[\"']?(\d{2,5})",
    r"\bEXPOSE\s+(\d{2,5})",
    r"\b--port[=\s]+(\d{2,5})",
]

FRAMEWORK_RULES: Dict[str, List[str]] = {
    "Next.js": ["next"],
    "React": ["react", "react-dom"],
    "Vite": ["vite"],
    "Express": ["express"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "Django": ["django"],
    "Spring Boot": ["spring-boot"],
    "NestJS": ["@nestjs/core"],
    "Vue": ["vue"],
    "Angular": ["@angular/core"],
    "Svelte": ["svelte"],
}

DATABASE_PATTERNS: Dict[str, List[str]] = {
    "PostgreSQL": ["postgres", "postgresql", "psycopg", "asyncpg", "pg"],
    "MySQL": ["mysql", "mysql2", "pymysql"],
    "MongoDB": ["mongodb", "mongoose", "pymongo"],
    "Redis": ["redis", "ioredis", "redis-py"],
    "SQLite": ["sqlite", "sqlite3"],
    "MariaDB": ["mariadb"],
    "Cassandra": ["cassandra"],
    "DynamoDB": ["dynamodb", "boto3"],
}

QUEUE_PATTERNS: Dict[str, List[str]] = {
    "RabbitMQ": ["rabbitmq", "amqp", "pika", "amqplib"],
    "Kafka": ["kafka", "confluent-kafka", "kafkajs"],
    "BullMQ": ["bullmq"],
    "Bull": ["bull"],
    "Celery": ["celery"],
    "AWS SQS": ["sqs"],
    "Google Pub/Sub": ["pubsub"],
}

CACHE_PATTERNS: Dict[str, List[str]] = {
    "Redis": ["redis", "ioredis", "redis-py"],
    "Memcached": ["memcached"],
}

STORAGE_PATTERNS: Dict[str, List[str]] = {
    "S3 / Object Storage": ["s3", "aws-sdk", "boto3", "minio", "objectstorage"],
}

SECRET_NAME_PATTERNS = re.compile(
    r"(PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|"
    r"ACCESS_KEY|CLIENT_SECRET|DATABASE_URL|DB_URL|JWT_SECRET|AWS_SECRET)",
    re.IGNORECASE
)

URL_ENV_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT)[A-Z0-9_]*)\b"
)


# =========================================================
# BASIC HELPERS
# =========================================================

def clean_path(path: str) -> str:
    path = str(path).replace("\\", "/")
    path = re.sub(r"^\./+", "", path)
    return path.strip("/")

def is_ignored(path: str) -> bool:
    parts = clean_path(path).split("/")
    return any(part.lower() in IGNORED_DIRECTORIES for part in parts)

def read_text_from_zip(archive: zipfile.ZipFile, filename: str, max_bytes: int = 1_500_000) -> str:
    try:
        info = archive.getinfo(filename)
        if info.file_size > max_bytes:
            return ""
        return archive.read(filename).decode("utf-8", errors="ignore")
    except Exception:
        return ""

def safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {}

def basename(path: str) -> str:
    return os.path.basename(clean_path(path)).lower()

def unique(items: List[Any]) -> List[Any]:
    result = []
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

def path_is_inside(path: str, directory: str) -> bool:
    path = clean_path(path)
    directory = clean_path(directory).strip("/")
    if not directory:
        return "/" not in path
    return path == directory or path.startswith(directory + "/")

def get_directories(files: List[str]) -> Dict[str, List[str]]:
    directories: Dict[str, List[str]] = {}
    for file in files:
        if is_ignored(file):
            continue
        parts = clean_path(file).split("/")
        if len(parts) <= 1:
            continue
        for index in range(1, len(parts)):
            directory_path = "/".join(parts[:index])
            directories.setdefault(directory_path, []).append(file)
    return directories

def directory_name(path: str) -> str:
    return clean_path(path).split("/")[-1]


# =========================================================
# MANIFEST / FRAMEWORK ANALYSIS
# =========================================================

def read_package_json(archive: zipfile.ZipFile, file: str) -> Dict[str, Any]:
    return safe_json(read_text_from_zip(archive, file))

def detect_manifest_type(directory_files: List[str]) -> str:
    names = {basename(file) for file in directory_files}
    if "package.json" in names: return "Node.js"
    if names.intersection({"requirements.txt", "pyproject.toml", "pipfile"}): return "Python"
    if names.intersection({"pom.xml", "build.gradle", "build.gradle.kts"}): return "Java"
    if "go.mod" in names: return "Go"
    if "cargo.toml" in names: return "Rust"
    if "gemfile" in names: return "Ruby"
    if "composer.json" in names: return "PHP"
    if any(name.endswith(".csproj") for name in names): return "C#"
    if names.intersection({"dockerfile", "containerfile"}): return "Container"
    return "Unknown"

def detect_frameworks(directory_files: List[str], archive: zipfile.ZipFile) -> List[str]:
    frameworks = []
    package_files = [file for file in directory_files if basename(file) == "package.json"]
    
    for package_file in package_files:
        package = read_package_json(archive, package_file)
        dependencies = {}
        dependencies.update(package.get("dependencies", {}) or {})
        dependencies.update(package.get("devDependencies", {}) or {})
        dependency_names = {str(key).lower() for key in dependencies.keys()}

        for framework, rules in FRAMEWORK_RULES.items():
            if any(rule.lower() in dependency_names for rule in rules):
                frameworks.append(framework)

    # Fast Source Scanning for Python/Java
    text = ""
    for file in directory_files:
        if file.lower().endswith(CODE_EXTENSIONS):
            text += "\n" + read_text_from_zip(archive, file, 400_000).lower()

    text_rules = {
        "FastAPI": ["from fastapi", "import fastapi"],
        "Flask": ["from flask", "import flask"],
        "Django": ["django"],
        "Spring Boot": ["springboot", "spring boot"]
    }

    for framework, rules in text_rules.items():
        if any(rule in text for rule in rules):
            frameworks.append(framework)

    return unique(frameworks)

def detect_service_technology(directory_files: List[str], archive: zipfile.ZipFile) -> str:
    manifest = detect_manifest_type(directory_files)
    if manifest in ("Node.js", "Python"):
        frameworks = detect_frameworks(directory_files, archive)
        if frameworks:
            return f"{manifest} / " + " + ".join(frameworks)
    return manifest

def detect_technologies(files: List[str], archive: zipfile.ZipFile) -> List[str]:
    technologies = []
    if any(basename(file) == "package.json" for file in files):
        technologies.append("Node.js / JavaScript")
    if any(basename(file) in {"requirements.txt", "pyproject.toml", "pipfile"} for file in files):
        technologies.append("Python")
    if any(basename(file) in {"dockerfile", "containerfile"} for file in files):
        technologies.append("Docker / OCI")
    if any(basename(file) in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"} for file in files):
        technologies.append("Docker Compose")
    if any(basename(file) == "pom.xml" for file in files):
        technologies.append("Java")
    if any(basename(file) == "go.mod" for file in files):
        technologies.append("Go")
    if any(basename(file) == "cargo.toml" for file in files):
        technologies.append("Rust")
    
    # K8s Detection
    for file in files:
        if file.lower().endswith((".yml", ".yaml")):
            text = read_text_from_zip(archive, file, 700_000)
            if re.search(r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service)\s*$", text):
                technologies.append("Kubernetes manifests")
                break

    return unique(technologies)


# =========================================================
# COMPOSE / KUBERNETES
# =========================================================

def detect_compose_files(files: List[str]) -> List[str]:
    names = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
    return [file for file in files if basename(file) in names]

def detect_kubernetes_files(files: List[str], archive: zipfile.ZipFile) -> List[str]:
    result = []
    for file in files:
        if not file.lower().endswith((".yml", ".yaml")):
            continue
        text = read_text_from_zip(archive, file, 700_000)
        if re.search(r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service)\s*$", text):
            result.append(file)
    return result

def parse_compose_services(archive: zipfile.ZipFile, compose_files: List[str]) -> List[Dict[str, Any]]:
    services: Dict[str, Dict[str, Any]] = {}

    for file in compose_files:
        text = read_text_from_zip(archive, file, 1_500_000)
        in_services = False
        current = None

        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue

            indent = len(raw) - len(raw.lstrip(" "))
            stripped = raw.strip()

            if stripped == "services:" and indent == 0:
                in_services = True
                current = None
                continue

            if not in_services:
                continue

            if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
                name = stripped[:-1].strip().strip("'\"")
                if name:
                    current = name
                    services.setdefault(name, {
                        "name": name, "file": file, "image": None, 
                        "build": None, "ports": [], "depends_on": [], "replicas": 1
                    })
                continue

            if current and current in services and indent >= 4:
                entry = services[current]
                if stripped.startswith("image:"):
                    entry["image"] = stripped.split(":", 1)[1].strip().strip("'\"")
                elif stripped.startswith("build:"):
                    entry["build"] = stripped.split(":", 1)[1].strip().strip("'\"")

    # Second pass for nested lists (ports, depends_on)
    for file in compose_files:
        text = read_text_from_zip(archive, file, 1_500_000)
        current = None
        in_services = False
        block = None

        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue

            indent = len(raw) - len(raw.lstrip(" "))
            stripped = raw.strip()

            if stripped == "services:" and indent == 0:
                in_services = True
                current = None
                block = None
                continue

            if not in_services: continue

            if indent == 2 and stripped.endswith(":"):
                current = stripped[:-1].strip().strip("'\"")
                block = None
                continue

            if not current or current not in services: continue

            if indent == 4:
                block = "ports" if stripped == "ports:" else "depends_on" if stripped == "depends_on:" else None
                replicas = re.match(r"replicas:\s*(\d+)", stripped)
                if replicas: services[current]["replicas"] = int(replicas.group(1))
                continue

            if indent >= 6 and block:
                if block == "ports":
                    match = re.search(r'["\']?(\d+)(?::(\d+))?', stripped)
                    if match:
                        port = int(match.group(2) or match.group(1))
                        if 1 <= port <= 65535:
                            services[current]["ports"].append(port)
                elif block == "depends_on":
                    dependency = stripped.lstrip("- ").strip().strip("'\"")
                    if re.match(r"^[A-Za-z0-9_.-]+$", dependency):
                        services[current]["depends_on"].append(dependency)

    for item in services.values():
        item["ports"] = unique(item["ports"])
        item["depends_on"] = unique(item["depends_on"])

    return list(services.values())

def parse_kubernetes_workloads(files: List[str], archive: zipfile.ZipFile) -> List[Dict[str, Any]]:
    workloads = []
    for file in files:
        if not file.lower().endswith((".yml", ".yaml")):
            continue
        text = read_text_from_zip(archive, file, 1_500_000)
        kind_match = re.search(r"(?m)^\s*kind\s*:\s*([A-Za-z0-9]+)\s*$", text)
        name_match = re.search(r"(?ms)metadata:\s*\n(?:\s+[^\n]+\n)*?\s+name\s*:\s*([A-Za-z0-9_.-]+)", text)
        replicas_match = re.search(r"(?m)^\s*replicas\s*:\s*(\d+)\s*$", text)

        if kind_match and name_match:
            kind = kind_match.group(1)
            if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
                workloads.append({
                    "name": name_match.group(1),
                    "kind": kind,
                    "replicas": int(replicas_match.group(1)) if replicas_match else 1,
                    "file": file
                })
    return workloads


# =========================================================
# SERVICE DETECTION
# =========================================================

def classify_directory(name: str, technology: str, directory_files: List[str], archive: zipfile.ZipFile) -> Optional[str]:
    name_lower = name.lower()
    if name_lower in FRONTEND_NAMES: return "frontend"
    if name_lower in BACKEND_NAMES: return "backend"
    if name_lower in WORKER_NAMES: return "worker"

    frameworks = detect_frameworks(directory_files, archive)
    framework_text = " ".join(frameworks).lower()
    if any(framework in framework_text for framework in ("react", "next.js", "vite", "vue", "angular", "svelte")):
        return "frontend"

    text = ""
    for file in directory_files[:80]:
        if file.lower().endswith(CODE_EXTENSIONS):
            text += "\n" + read_text_from_zip(archive, file, 150_000).lower()

    if any(term in text for term in ("bullmq", "celery", "rq.worker", "consumer(", "kafkaconsumer", "rabbitmq", "background_tasks", "dramatiq")):
        return "worker"

    if technology != "Unknown": return "backend"
    return None

def detect_services(files: List[str], archive: zipfile.ZipFile, compose_services: List[Dict], k8s_workloads: List[Dict]) -> List[Dict[str, Any]]:
    services = []
    directories = get_directories(files)

    for path, directory_files in directories.items():
        name = directory_name(path)
        technology = detect_service_technology(directory_files, archive)
        service_type = classify_directory(name, technology, directory_files, archive)

        if service_type:
            services.append({
                "name": name,
                "technology": technology,
                "type": service_type,
                "directory": path,
                "frameworks": detect_frameworks(directory_files, archive)
            })

    # Root-level application
    root_files = [file for file in files if "/" not in file]
    root_technology = detect_service_technology(root_files, archive)
    if root_technology != "Unknown":
        root_type = classify_directory("application", root_technology, root_files, archive) or "backend"
        if not any(service["directory"] == "." for service in services):
            services.append({
                "name": "application",
                "technology": root_technology,
                "type": root_type,
                "directory": ".",
                "frameworks": detect_frameworks(root_files, archive)
            })

    # Merge Compose services
    existing_names = {service["name"].lower() for service in services}
    for item in compose_services:
        if item["name"].lower() in existing_names: continue
        name_lower = item["name"].lower()
        service_type = "frontend" if name_lower in FRONTEND_NAMES else "worker" if name_lower in WORKER_NAMES else "backend"
        
        technology = "Container"
        if item.get("image"):
            image = item["image"].lower()
            if "node" in image: technology = "Node.js"
            elif "python" in image: technology = "Python"
            elif "nginx" in image: technology = "Nginx"

        services.append({
            "name": item["name"],
            "technology": technology,
            "type": service_type,
            "directory": item.get("build") or "",
            "frameworks": []
        })

    # Merge K8s workloads
    existing_names = {service["name"].lower() for service in services}
    for item in k8s_workloads:
        if item["name"].lower() in existing_names: continue
        name_lower = item["name"].lower()
        service_type = "worker" if any(name in name_lower for name in WORKER_NAMES) else "frontend" if any(name in name_lower for name in FRONTEND_NAMES) else "backend"

        services.append({
            "name": item["name"],
            "technology": "Kubernetes",
            "type": service_type,
            "directory": "",
            "frameworks": [],
            "declared_replicas": item["replicas"]
        })

    return unique(services)


# =========================================================
# DEPENDENCY DETECTION (EVIDENCE-BASED)
# =========================================================

def detect_dependencies_with_evidence(files: List[str], archive: zipfile.ZipFile) -> Tuple[Dict[str, List[str]], Dict[str, Any]]:
    """
    Scans files line-by-line. Does NOT concatenate code into a giant string.
    Returns highly confident dependency associations with line snippets.
    """
    dependencies: Dict[str, Set[str]] = {
        "databases": set(),
        "queues": set(),
        "caches": set(),
        "object_storage": set(),
        "external_services": set()
    }

    evidence: Dict[str, List[Dict[str, Any]]] = {
        "databases": [],
        "queues": [],
        "caches": [],
        "object_storage": []
    }
    
    urls = set()

    # Mapping engine for line-by-line checks
    search_map = {
        "databases": DATABASE_PATTERNS,
        "queues": QUEUE_PATTERNS,
        "caches": CACHE_PATTERNS,
        "object_storage": STORAGE_PATTERNS
    }

    for file in files:
        if is_ignored(file): continue

        filename = os.path.basename(file).lower()

        # Strict Manifest Parsing
        if filename == "package.json":
            pkg = parse_json_safe(read_text_from_zip(archive, file))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            
            for category, mapping in search_map.items():
                for sys_name, triggers in mapping.items():
                    if any(t in deps for t in triggers):
                        dependencies[category].add(sys_name)
                        evidence[category].append({
                            "technology": sys_name,
                            "file": file,
                            "snippet": f'"{list(set(deps.keys()).intersection(triggers))[0]}" in package.json',
                            "confidence": 0.99
                        })

        # Deep Source Code Scanning
        elif file.lower().endswith(SOURCE_EXTENSIONS):
            content = read_text_from_zip(archive, file, 500_000)
            if not content: continue

            lines = content.splitlines()
            for line_idx, line in enumerate(lines):
                line_lower = line.lower()
                if len(line_lower) > 500: continue # Skip minified

                # Look for URLs
                for match in re.findall(r"https?://[A-Za-z0-9._:-]+", line):
                    try:
                        host = urlparse(match).hostname
                        if host and host not in {"localhost", "127.0.0.1"}:
                            urls.add(host)
                    except Exception: pass

                # Look for DBs, Queues, Caches in import statements or connections
                if any(k in line_lower for k in ("import ", "require(", "connect(", "client(", "://" )):
                    for category, mapping in search_map.items():
                        for sys_name, triggers in mapping.items():
                            if any(t in line_lower for t in triggers):
                                dependencies[category].add(sys_name)
                                evidence[category].append({
                                    "technology": sys_name,
                                    "file": file,
                                    "line": line_idx + 1,
                                    "snippet": line.strip()[:100],
                                    "confidence": 0.90
                                })

    dependencies["external_services"] = set(sorted(list(urls))[:50])

    # Convert sets to lists and deduplicate evidence
    final_deps = {k: list(v) for k, v in dependencies.items()}
    final_evidence = {k: unique(v)[:10] for k, v in evidence.items()} # limit evidence to top 10

    return final_deps, final_evidence

def parse_json_safe(content: str) -> Dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


# =========================================================
# ENVIRONMENT / SECRETS
# =========================================================

def detect_environment(files: List[str], archive: zipfile.ZipFile) -> Dict[str, Any]:
    env_files = []
    variables = []
    potential_secrets = []
    recognized_env_names = {".env", ".env.local", ".env.production", ".env.development", ".env.example", ".env.sample"}

    for file in files:
        name = basename(file)
        if name in recognized_env_names or name.startswith(".env") or name.endswith(".env"):
            env_files.append(file)
            content = read_text_from_zip(archive, file, 300_000)

            for raw in content.splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                key, _, value = line.partition("=")
                key = key.strip()
                if not key: continue

                variables.append(key)
                if SECRET_NAME_PATTERNS.search(key):
                    potential_secrets.append({
                        "file": file,
                        "variable": key,
                        "value_exposed": bool(value.strip())
                    })

    return {
        "files": unique(env_files),
        "variables": unique(variables),
        "potential_secrets": potential_secrets
    }


# =========================================================
# PORT / HEALTH DETECTION
# =========================================================

def detect_ports(files: List[str], archive: zipfile.ZipFile) -> List[int]:
    ports = set()
    for file in files:
        if is_ignored(file): continue
        if not file.lower().endswith((".js", ".ts", ".jsx", ".tsx", ".py", ".yml", ".yaml", ".env", ".dockerfile", "dockerfile", ".json")):
            continue
        content = read_text_from_zip(archive, file, 500_000)
        for pattern in PORT_PATTERNS:
            for match in re.findall(pattern, content, flags=re.IGNORECASE):
                try:
                    port = int(match)
                    if 1 <= port <= 65535: ports.add(port)
                except ValueError: pass
    return sorted(list(ports))

def detect_health_endpoints(files: List[str], archive: zipfile.ZipFile) -> List[str]:
    endpoints = set()
    for file in files:
        if is_ignored(file): continue
        if not file.lower().endswith(CODE_EXTENSIONS): continue
        content = read_text_from_zip(archive, file)
        endpoints.update(HEALTH_ROUTE_PATTERN.findall(content))
    return sorted(list(endpoints))

def detect_service_health(services: List[Dict], files: List[str], archive: zipfile.ZipFile) -> Dict[str, str]:
    service_health = {}
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        if directory in ("", "."): service_files = [file for file in files if "/" not in file]
        else: service_files = [file for file in files if file.startswith(directory + "/")]

        for file in service_files:
            if not file.lower().endswith(CODE_EXTENSIONS): continue
            content = read_text_from_zip(archive, file, 400_000)
            matches = HEALTH_ROUTE_PATTERN.findall(content)
            if matches:
                service_health[service["name"]] = matches[0]
                break
    return service_health


# =========================================================
# INFRASTRUCTURE DETECTION
# =========================================================

def detect_docker(files: List[str]) -> List[str]:
    return [file for file in files if basename(file) in {"dockerfile", "containerfile"}]

def detect_zerops(files: List[str]) -> List[str]:
    return [file for file in files if basename(file) in {"zerops.yml", "zerops.yaml"}]

def detect_ci_cd(files: List[str]) -> List[str]:
    results = []
    for file in files:
        path = clean_path(file).lower()
        if path.startswith(".github/workflows/") or path.startswith(".gitlab-ci") or basename(path) in {"jenkinsfile", "azure-pipelines.yml", "circleci"}:
            results.append(file)
    return results

def detect_iac(files: List[str]) -> List[str]:
    results = []
    for file in files:
        name = basename(file)
        if name.endswith(".tf") or name in {"pulumi.yaml", "pulumi.yml", "serverless.yml", "serverless.yaml"}:
            results.append(file)
    return results


# =========================================================
# SERVICE REFERENCE DETECTION
# =========================================================

def detect_service_urls(services: List[Dict], files: List[str], archive: zipfile.ZipFile) -> List[Dict[str, str]]:
    service_refs = []
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        if directory in ("", "."): relevant = [file for file in files if "/" not in file]
        else: relevant = [file for file in files if file.startswith(directory + "/")]

        text = ""
        for file in relevant[:150]:
            if file.lower().endswith(SOURCE_EXTENSIONS):
                text += "\n" + read_text_from_zip(archive, file, 250_000)

        for variable in unique(URL_ENV_PATTERN.findall(text)):
            if any(token in variable for token in ("DATABASE", "DB_", "REDIS", "S3", "AWS_", "KAFKA", "RABBIT", "QUEUE", "MONGO", "POSTGRES", "MYSQL")):
                continue
            service_refs.append({"service": service["name"], "variable": variable})
    return service_refs


# =========================================================
# DETERMINISTIC ARCHITECTURE GRAPH
# =========================================================

def build_architecture(services: List[Dict], dependencies: Dict[str, List[str]], dependency_evidence: Dict[str, Any], compose_services: List[Dict], service_url_references: List[Dict[str, str]]) -> Dict[str, Any]:
    nodes = []
    connections = []

    # 1. Map Core Nodes
    for service in services:
        nodes.append({
            "name": service["name"],
            "type": service["type"],
            "technology": service["technology"],
            "replicas": service.get("declared_replicas", 1)
        })

    # Add DBs, Queues, Caches
    for db in dependencies["databases"]: nodes.append({"name": db.lower(), "type": "database", "technology": db})
    for queue in dependencies["queues"]: nodes.append({"name": queue.lower().replace(" ", "-"), "type": "queue", "technology": queue})
    for cache in dependencies["caches"]: nodes.append({"name": cache.lower(), "type": "cache", "technology": cache})
    for storage in dependencies["object_storage"]: nodes.append({"name": storage.lower().replace(" ", "-"), "type": "object_storage", "technology": storage})

    # 2. Evidence-Based Connections
    # A. Docker Compose Explicit Links
    for compose in compose_services:
        for dependency in compose.get("depends_on", []):
            connections.append({
                "from": compose["name"],
                "to": dependency,
                "relationship": "depends_on",
                "inference": "Docker Compose Configuration"
            })

    # B. Directory-Based Evidence Linking
    for category in ["databases", "queues", "caches", "object_storage"]:
        for ev in dependency_evidence.get(category, []):
            ev_file = ev["file"]
            target_tech = ev["technology"].lower().replace(" ", "-")
            
            # Find which service owns this file
            for service in services:
                svc_dir = service.get("directory", "")
                if svc_dir and (ev_file.startswith(svc_dir + "/") or svc_dir == "."):
                    connections.append({
                        "from": service["name"],
                        "to": target_tech,
                        "relationship": "uses",
                        "inference": f"Source Evidence in {ev_file}"
                    })

    # C. Service-to-Service Env Var Linking (e.g. FRONTEND_URL in backend code)
    for ref in service_url_references:
        # If variable name roughly matches another service name
        var_name = ref["variable"].lower()
        for svc in services:
            if svc["name"].lower() in var_name and svc["name"] != ref["service"]:
                connections.append({
                    "from": ref["service"],
                    "to": svc["name"],
                    "relationship": "request",
                    "inference": f"Environment Variable Mapping ({ref['variable']})"
                })

    # D. Fallback (Only if completely isolated)
    frontends = [s for s in services if s["type"] == "frontend"]
    backends = [s for s in services if s["type"] == "backend"]
    
    # If a frontend has no outbound connections, link to a backend as a fallback
    for frontend in frontends:
        has_connection = any(c["from"] == frontend["name"] for c in connections)
        if not has_connection and backends:
            connections.append({
                "from": frontend["name"],
                "to": backends[0]["name"],
                "relationship": "request",
                "inference": "Fallback Inferred Path"
            })

    return {
        "nodes": unique(nodes),
        "connections": unique(connections)
    }


# =========================================================
# FAILURE SCENARIOS & RELIABILITY ENGINE
# =========================================================

def build_failure_scenarios(services: List[Dict], dependencies: Dict[str, List[str]]) -> List[Dict[str, str]]:
    scenarios = []
    for service in services:
        service_type = "worker" if service["type"] == "worker" else service["type"]
        scenarios.append({"id": service["name"], "type": "service_failure", "target": service["name"], "label": f"{service['name']} Failure", "description": f"Simulate failure of the {service_type} service."})
    for database in dependencies["databases"]: scenarios.append({"id": f"database:{database}", "type": "database_failure", "target": database, "label": f"{database} Failure", "description": f"Simulate loss of the {database} dependency."})
    for queue in dependencies["queues"]: scenarios.append({"id": f"queue:{queue}", "type": "queue_failure", "target": queue, "label": f"{queue} Failure", "description": f"Simulate loss of the {queue} messaging layer."})
    for cache in dependencies["caches"]: scenarios.append({"id": f"cache:{cache}", "type": "cache_failure", "target": cache, "label": f"{cache} Failure", "description": f"Simulate loss of the {cache} cache layer."})
    
    scenarios.append({"id": "traffic", "type": "traffic_spike", "target": "all", "label": "Traffic Spike ×10", "description": "Simulate a tenfold increase in incoming traffic."})
    scenarios.append({"id": "cascading", "type": "cascading_failure", "target": "critical-path", "label": "Cascading Failure", "description": "Simulate failure propagation through the inferred dependency graph."})
    return scenarios

def make_finding(severity: str, category: str, title: str, description: str, recommendation: str, score_impact: int) -> Dict[str, Any]:
    return {"severity": severity, "category": category, "title": title, "description": description, "recommendation": recommendation, "score_impact": score_impact}

def analyze_reliability(services: List[Dict], dependencies: Dict[str, List[str]], health_endpoints: List[str], service_health: Dict[str, str], dockerfiles: List[str], zerops_configs: List[str], compose_services: List[Dict], k8s_workloads: List[Dict], env_info: Dict[str, Any], ci_cd: List[str], iac: List[str]) -> List[Dict[str, Any]]:
    findings = []
    frontends = [s for s in services if s["type"] == "frontend"]
    workers = [s for s in services if s["type"] == "worker"]

    for service in services:
        replicas = service.get("declared_replicas", 1)
        if service["type"] == "backend" and replicas < 2:
            findings.append(make_finding("critical", "availability", f"{service['name']} Single Point of Failure", f"Only one instance is statically represented for {service['name']}. A single instance can become a complete request-path failure.", f"Run at least 2 {service['name']} instances behind a health-aware load balancer.", 25))
        elif service["type"] == "worker" and replicas < 2:
            findings.append(make_finding("warning", "availability", f"{service['name']} Worker Redundancy Not Detected", f"No redundant {service['name']} worker instances were detected.", f"Run multiple {service['name']} workers and use durable queue semantics where applicable.", 10))
        elif service["type"] == "frontend" and replicas < 2 and len(frontends) == 1:
            findings.append(make_finding("warning", "availability", f"{service['name']} Frontend Redundancy Not Detected", "Only one frontend service/instance is represented.", "Use redundant frontend instances or a highly available static/CDN deployment.", 8))

    if not health_endpoints:
        findings.append(make_finding("warning", "observability", "Health Check Not Detected", "No common application health endpoint was detected.", "Expose /health or /healthz and configure deployment health checks.", 10))
    else:
        missing = [s["name"] for s in services if s["type"] in {"backend", "worker"} and s["name"] not in service_health]
        if missing:
            findings.append(make_finding("warning", "observability", "Some Services Lack Health Checks", "Health endpoints exist somewhere in the project, but not every backend/worker service has a service-specific endpoint detected.", "Add service-specific health/readiness checks where appropriate.", 5))

    for database in dependencies["databases"]:
        findings.append(make_finding("warning", "data", f"{database} Availability Must Be Reviewed", f"{database} is a detected application dependency. Static analysis cannot confirm whether the database is replicated or highly available.", f"Review {database} backups, replication, failover, connection pooling and recovery requirements.", 8))

    if workers and not dependencies["queues"]:
        findings.append(make_finding("warning", "async", "Worker Queue Not Detected", "Background worker-like services were found but no obvious durable messaging infrastructure was detected.", "Consider a durable queue to absorb bursts and isolate producer/consumer failures.", 8))

    if not dockerfiles and not compose_services and not k8s_workloads:
        findings.append(make_finding("info", "deployment", "Container / Orchestration Configuration Not Detected", "No Dockerfile, Compose service definition or Kubernetes workload was detected.", "Add explicit deployment configuration for reproducible production deployment.", 3))
    
    if zerops_configs: findings.append(make_finding("info", "deployment", "Existing Zerops Configuration Detected", "A Zerops configuration file already exists in the project.", "Compare the existing configuration with the generated optimization plan.", 0))

    exposed_secrets = [item for item in env_info["potential_secrets"] if item["value_exposed"]]
    if exposed_secrets:
        findings.append(make_finding("critical", "security", "Potential Secrets Found in Environment Files", f"{len(exposed_secrets)} secret-like environment variables appear to have values in uploaded files.", "Do not commit real credentials. Rotate exposed secrets and use deployment secret management.", 20))

    if not ci_cd: findings.append(make_finding("info", "delivery", "CI/CD Configuration Not Detected", "No common CI/CD workflow was detected.", "Add automated build, test and deployment checks before production rollout.", 3))
    if not iac: findings.append(make_finding("info", "infrastructure", "Infrastructure-as-Code Not Detected", "No Terraform/Pulumi-style infrastructure configuration was detected.", "Consider versioning infrastructure configuration when infrastructure complexity grows.", 2))
    
    if not services:
        findings.append(make_finding("critical", "analysis", "Application Service Could Not Be Identified", "The analyzer could not confidently identify an application service.", "Use conventional service directories, a supported manifest, Compose, or Kubernetes configuration.", 30))

    return findings

def calculate_score(findings: List[Dict[str, Any]]) -> int:
    score = 100
    for item in findings: score -= int(item.get("score_impact", 0))
    return max(0, min(100, score))

def calculate_risk_summary(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"critical": 0, "warning": 0, "info": 0}
    for finding in findings:
        severity = finding.get("severity")
        if severity in counts: counts[severity] += 1

    if counts["critical"] > 0: level = "critical"
    elif counts["warning"] >= 3: level = "high"
    elif counts["warning"] > 0: level = "moderate"
    else: level = "low"

    return {"level": level, "critical": counts["critical"], "warning": counts["warning"], "info": counts["info"]}


# =========================================================
# BOTTLENECK ENGINE
# =========================================================

def detect_bottlenecks(services: List[Dict], dependencies: Dict[str, List[str]], findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates = []
    for service in services:
        if service["type"] == "backend":
            candidates.append({"component": service["name"], "type": "service", "risk": "high", "reason": "Backend services sit on the primary request path and are treated as single-instance unless deployment metadata says otherwise.", "priority": 90})

    for database in dependencies["databases"]: candidates.append({"component": database, "type": "database", "risk": "high", "reason": "Detected database dependency can constrain availability and throughput.", "priority": 85})
    for queue in dependencies["queues"]: candidates.append({"component": queue, "type": "queue", "risk": "medium", "reason": "Messaging infrastructure can become a throughput or backlog bottleneck.", "priority": 70})
    for cache in dependencies["caches"]: candidates.append({"component": cache, "type": "cache", "risk": "medium", "reason": "Cache availability or saturation can affect latency and dependency load.", "priority": 60})

    for item in findings:
        if item["severity"] == "critical":
            candidates.append({"component": item["title"], "type": "finding", "risk": "critical", "reason": item["description"], "priority": 95})

    candidates.sort(key=lambda item: item["priority"], reverse=True)
    return candidates[:10]


# =========================================================
# OPTIMIZATION PLAN
# =========================================================

def build_optimization_plan(services: List[Dict], dependencies: Dict[str, List[str]], deployment: Dict[str, Any]) -> List[Dict[str, str]]:
    actions = []
    for service in services:
        replicas = service.get("declared_replicas", 1)
        if service["type"] in {"backend", "worker", "frontend"} and replicas < 2:
            actions.append({"priority": "high" if service["type"] == "backend" else "medium", "service": service["name"], "action": "Increase redundancy", "current": f"{replicas} detected instance(s)", "recommended": "2+ instances", "reason": "Reduces the chance that one instance failure takes the service offline."})

        if service["name"] not in deployment.get("service_health", {}) and service["type"] in {"backend", "worker"}:
            actions.append({"priority": "medium", "service": service["name"], "action": "Add health/readiness checks", "current": "No service-specific health endpoint detected", "recommended": "/health or /healthz", "reason": "Unhealthy instances can be removed from traffic."})

    if dependencies["databases"]: actions.append({"priority": "high", "service": "database layer", "action": "Review database high availability", "current": ", ".join(dependencies["databases"]), "recommended": "Backups + replication/failover appropriate to workload", "reason": "Application redundancy does not remove a database dependency bottleneck."})
    
    if any(service["type"] == "worker" for service in services) and not dependencies["queues"]:
        actions.append({"priority": "medium", "service": "worker infrastructure", "action": "Introduce durable queueing", "current": "No queue detected", "recommended": "Durable queue + retry/dead-letter strategy", "reason": "Separates request producers from background consumers."})

    if not deployment.get("dockerfiles") and not deployment.get("compose_files") and not deployment.get("kubernetes_files"):
        actions.append({"priority": "medium", "service": "deployment", "action": "Add explicit deployment configuration", "current": "No container/orchestration configuration detected", "recommended": "Containerized deployment definition", "reason": "Makes deployment reproducible and easier to optimize."})

    if not deployment.get("ci_cd"):
        actions.append({"priority": "low", "service": "delivery", "action": "Add CI/CD validation", "current": "No CI/CD configuration detected", "recommended": "Automated build + test + deployment checks", "reason": "Prevents known reliability problems from reaching production."})

    return actions


# =========================================================
# ZEROPS CONFIG GENERATOR
# =========================================================

def zerops_technology(service: Dict[str, Any]) -> str:
    technology = (service.get("technology") or "").lower()
    if "python" in technology: return "python"
    if "java" in technology: return "java"
    if "go" in technology: return "go"
    if "rust" in technology: return "rust"
    return "nodejs"

def sanitize_yaml_value(value: Any) -> str:
    return str(value).replace("\n", " ").strip().replace('"', '\\"')

def generate_zerops_config(services: List[Dict], service_health: Dict[str, str]) -> str:
    lines = [
        "# Generated by Zerops Autopilot",
        "# Static analysis recommendation - review before production use.",
        "", "project:", "  name: optimized-application", "", "services:"
    ]

    for service in services:
        name = sanitize_yaml_value(service["name"])
        technology = zerops_technology(service)
        lines.append(f'  - name: "{name}"')
        lines.append(f"    technology: {technology}")
        
        if service["type"] in {"backend", "worker", "frontend"}:
            lines.append("    replicas: 2")
            
        health = service_health.get(service["name"])
        if health:
            lines.append("    healthCheck:")
            lines.append(f'      path: "{sanitize_yaml_value(health)}"')
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# =========================================================
# SUMMARY
# =========================================================

def build_summary(services: List[Dict], technologies: List[str], dependencies: Dict[str, List[str]], score: int, risk_summary: Dict[str, Any], bottlenecks: List[Dict[str, Any]]) -> Dict[str, Any]:
    service_counts = {
        "frontend": len([s for s in services if s["type"] == "frontend"]),
        "backend": len([s for s in services if s["type"] == "backend"]),
        "worker": len([s for s in services if s["type"] == "worker"])
    }

    return {
        "headline": "Architecture requires reliability improvements" if (risk_summary["critical"] or risk_summary["warning"]) else "Architecture appears structurally healthy",
        "reliability_score": score,
        "risk_level": risk_summary["level"],
        "service_counts": service_counts,
        "technology_count": len(technologies),
        "database_count": len(dependencies["databases"]),
        "queue_count": len(dependencies["queues"]),
        "cache_count": len(dependencies["caches"]),
        "top_bottleneck": bottlenecks[0]["component"] if bottlenecks else None
    }


# =========================================================
# API
# =========================================================

@app.get("/")
def home():
    return jsonify({"service": "Zerops Autopilot Analyzer", "status": "running", "version": VERSION, "mode": "static-analysis", "ai_required": False, "database_required": False})

@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({"status": "healthy", "service": "zerops-autopilot-analyzer", "version": VERSION})

@app.post("/analyze-project")
def analyze_project():
    if "project" not in request.files: return jsonify({"error": "No project file received"}), 400
    project = request.files["project"]
    if not project.filename: return jsonify({"error": "Uploaded project has no filename"}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "project.zip")
        project.save(zip_path)

        if not zipfile.is_zipfile(zip_path): return jsonify({"error": "Uploaded file is not a valid ZIP archive"}), 400

        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                files = [clean_path(name) for name in archive.namelist() if not name.endswith("/") and clean_path(name) and not is_ignored(name)]

                technologies = detect_technologies(files, archive)
                compose_files = detect_compose_files(files)
                compose_services = parse_compose_services(archive, compose_files)
                kubernetes_files = detect_kubernetes_files(files, archive)
                k8s_workloads = parse_kubernetes_workloads(kubernetes_files, archive)
                
                services = detect_services(files, archive, compose_services, k8s_workloads)
                
                # New Enterprise Evidence Engine
                dependencies, dependency_evidence = detect_dependencies_with_evidence(files, archive)
                
                ports = detect_ports(files, archive)
                health_endpoints = detect_health_endpoints(files, archive)
                service_health = detect_service_health(services, files, archive)
                dockerfiles = detect_docker(files)
                zerops_configs = detect_zerops(files)
                ci_cd = detect_ci_cd(files)
                iac = detect_iac(files)
                env_info = detect_environment(files, archive)
                service_url_references = detect_service_urls(services, files, archive)

                # New Enterprise Directed Graph Builder
                architecture = build_architecture(services, dependencies, dependency_evidence, compose_services, service_url_references)

                findings = analyze_reliability(services, dependencies, health_endpoints, service_health, dockerfiles, zerops_configs, compose_services, k8s_workloads, env_info, ci_cd, iac)
                reliability_score = calculate_score(findings)
                risk_summary = calculate_risk_summary(findings)
                bottlenecks = detect_bottlenecks(services, dependencies, findings)

                deployment = {
                    "ports": ports,
                    "health_endpoints": health_endpoints,
                    "health_endpoints_by_service": service_health,
                    "service_health": service_health,
                    "dockerfiles": dockerfiles,
                    "zerops_configs": zerops_configs,
                    "compose_files": compose_files,
                    "kubernetes_files": kubernetes_files,
                    "ci_cd": ci_cd,
                    "iac": iac,
                    "environment_files": env_info["files"]
                }

                optimization_plan = build_optimization_plan(services, dependencies, deployment)
                zerops_yml = generate_zerops_config(services, service_health)
                failure_scenarios = build_failure_scenarios(services, dependencies)
                summary = build_summary(services, technologies, dependencies, reliability_score, risk_summary, bottlenecks)

                response = {
                    "status": "success",
                    "analyzer": {"name": "Zerops Autopilot Analyzer", "version": VERSION, "mode": "static-analysis", "ai_required": False, "database_required": False},
                    "project": project.filename,
                    "file_count": len(files),
                    "summary": summary,
                    "technologies": technologies,
                    "services": services,
                    "dependencies": dependencies,
                    "dependency_evidence": dependency_evidence,
                    "deployment": deployment,
                    "environment": {
                        "files": env_info["files"],
                        "variable_count": len(env_info["variables"]),
                        "variables": env_info["variables"][:200],
                        "potential_secrets": env_info["potential_secrets"]
                    },
                    "service_url_references": service_url_references,
                    "compose_services": compose_services,
                    "kubernetes_workloads": k8s_workloads,
                    "architecture": architecture,
                    "failure_scenarios": failure_scenarios,
                    "reliability_score": reliability_score,
                    "risk_summary": risk_summary,
                    "findings": findings,
                    "bottlenecks": bottlenecks,
                    "optimization_plan": optimization_plan,
                    "zeropsYml": zerops_yml,
                    "files": files[:200]
                }

        except zipfile.BadZipFile: return jsonify({"error": "The uploaded ZIP file is corrupted"}), 400
        except Exception as error:
            app.logger.exception("Project analysis failed")
            return jsonify({"error": "Project analysis failed", "details": str(error)}), 500

    return jsonify(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)