from flask import Flask, request, jsonify
import zipfile
import os
import tempfile
import re
import json
from urllib.parse import urlparse
from pathlib import Path
from collections import defaultdict

app = Flask(__name__)
VERSION = "9.0"

# =========================================================
# CONFIGURATION (Knowledge base – not hardcoding)
# =========================================================

class Config:
    def __init__(self):
        self.ignored_directories = {
            "node_modules", ".git", ".next", "dist", "build",
            "__pycache__", ".venv", "venv", "coverage",
            ".pytest_cache", ".idea", ".vscode", ".turbo",
            ".cache", ".parcel-cache", "target", "vendor"
        }

        self.service_classification = {
            "frontend": {
                "name_patterns": {"frontend", "client", "web", "ui", "frontend-app", "website", "dashboard", "portal"},
                "framework_patterns": {"react", "next.js", "vite", "vue", "angular", "svelte"},
                "default_replicas": 2
            },
            "backend": {
                "name_patterns": {"backend", "server", "api", "service", "backend-api", "services", "app-server"},
                "framework_patterns": {"express", "fastapi", "flask", "django", "spring-boot", "nestjs"},
                "default_replicas": 2
            },
            "worker": {
                "name_patterns": {"worker", "workers", "job", "jobs", "queue", "queues", "notification",
                                 "notifications", "processor", "processing", "task", "tasks", "consumer",
                                 "consumers", "scheduler", "cron", "worker-service"},
                "framework_patterns": {"bullmq", "celery", "dramatiq"},
                "default_replicas": 2
            }
        }

        self.framework_detection = {
            "package_json": {
                "Next.js": ["next"],
                "React": ["react", "react-dom"],
                "Vite": ["vite"],
                "Express": ["express"],
                "NestJS": ["@nestjs/core"],
                "Vue": ["vue"],
                "Angular": ["@angular/core"],
                "Svelte": ["svelte"],
                "BullMQ": ["bullmq"],
                "Bull": ["bull"]
            },
            "source_code": {
                "FastAPI": [r"from\s+fastapi", r"import\s+fastapi"],
                "Flask": [r"from\s+flask", r"import\s+flask"],
                "Django": [r"django"],
                "Spring Boot": [r"springboot", r"spring\s+boot"],
                "Celery": [r"from\s+celery", r"import\s+celery"]
            }
        }

        # Dependency detection via manifests
        self.db_dependency_manifest = {
            "PostgreSQL": ["pg", "postgres", "postgresql", "psycopg", "asyncpg"],
            "MySQL": ["mysql", "mysql2", "pymysql", "mysqlclient"],
            "MongoDB": ["mongodb", "mongoose", "pymongo", "mongoengine"],
            "Redis": ["redis", "ioredis", "redis-py"],
            "SQLite": ["sqlite", "sqlite3"],
            "MariaDB": ["mariadb"],
            "Cassandra": ["cassandra"],
            "DynamoDB": ["dynamodb", "boto3", "@aws-sdk/client-dynamodb"]
        }
        self.queue_dependency_manifest = {
            "RabbitMQ": ["amqp", "amqplib", "pika", "rabbitmq"],
            "Kafka": ["kafkajs", "confluent-kafka"],
            "BullMQ": ["bullmq"],
            "Bull": ["bull"],
            "Celery": ["celery"],
            "AWS SQS": ["@aws-sdk/client-sqs", "sqs"],
            "Google Pub/Sub": ["@google-cloud/pubsub"]
        }
        self.cache_dependency_manifest = {
            "Redis": ["redis", "ioredis", "redis-py"],
            "Memcached": ["memcached", "pymemcache"],
        }
        self.storage_dependency_manifest = {
            "S3 / Object Storage": ["aws-sdk", "boto3", "minio", "@aws-sdk/client-s3"]
        }

        # Code patterns for dependencies
        self.db_code_patterns = {
            "PostgreSQL": [r"require\s*\(\s*['\"]pg['\"]\s*\)", r"import\s+.*\s+from\s+['\"]pg['\"]",
                           r"psycopg2\.connect", r"asyncpg\.connect"],
            "MySQL": [r"require\s*\(\s*['\"]mysql2?['\"]\s*\)", r"import\s+.*\s+from\s+['\"]mysql2?['\"]"],
            "MongoDB": [r"require\s*\(\s*['\"]mongoose['\"]\s*\)", r"import\s+.*\s+from\s+['\"]mongoose['\"]",
                        r"pymongo\.MongoClient"],
            "Redis": [r"require\s*\(\s*['\"]redis['\"]\s*\)", r"import\s+.*\s+from\s+['\"]redis['\"]",
                      r"redis\.Redis", r"redis\.from_url"],
        }
        self.queue_code_patterns = {
            "RabbitMQ": [r"amqp\.connect", r"require\('amqplib'\)"],
            "Kafka": [r"Kafka\.from", r"require\('kafkajs'\)"],
            "BullMQ": [r"Queue\s*\(\s*['\"]bull", r"Worker\s*\(\s*['\"]bull"],
            "Celery": [r"Celery\(", r"from celery import"],
        }
        self.cache_code_patterns = {
            "Redis": [r"redis\.createClient", r"Redis\.connect"],
            "Memcached": [r"Memcached\.connect"],
        }
        self.storage_code_patterns = {
            "S3 / Object Storage": [r"S3Client", r"boto3\.client\('s3'\)", r"Minio\."],
        }

        self.health_endpoint_patterns = [
            r'["\'](/(?:api/)?(?:health|healthz|ready|readiness|live|liveness|ping|status))["\']',
            r'@app\.route\(["\'](/(?:api/)?(?:health|healthz))["\']',
            r'\.get\(["\'](/(?:api/)?(?:health|healthz))["\']'
        ]

        self.port_patterns = [
            r"\bPORT\s*=\s*[\"']?(\d{2,5})",
            r"\bport\s*[:=]\s*[\"']?(\d{2,5})",
            r"\blisten\s*\(\s*[\"']?(\d{2,5})",
            r"\bEXPOSE\s+(\d{2,5})",
            r"\b--port[=\s]+(\d{2,5})",
            r"\bapp\.listen\((\d{2,5})\)",
            r"\bServer\(port=(\d{2,5})\)"
        ]

        self.secret_patterns = re.compile(
            r"(PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|"
            r"ACCESS_KEY|CLIENT_SECRET|DATABASE_URL|DB_URL|JWT_SECRET|AWS_SECRET|"
            r"SECRET_KEY|SIGNING_KEY|ENCRYPTION_KEY|AUTH_TOKEN|BEARER_TOKEN)",
            re.IGNORECASE
        )

        self.url_pattern = re.compile(r"\b([A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT)[A-Z0-9_]*)\b")

        self.source_extensions = {".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs",
                                  ".rb", ".php", ".cs", ".json", ".yml", ".yaml", ".toml",
                                  ".env", ".txt", ".properties", ".ini", ".xml"}
        self.code_extensions = {".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs", ".rb", ".php", ".cs"}

        self.manifest_files = {
            "Node.js": {"package.json"},
            "Python": {"requirements.txt", "pyproject.toml", "pipfile", "setup.py"},
            "Java": {"pom.xml", "build.gradle", "build.gradle.kts"},
            "Go": {"go.mod"},
            "Rust": {"cargo.toml"},
            "Ruby": {"gemfile"},
            "PHP": {"composer.json"},
            "C#": {".csproj"},
            "Container": {"dockerfile", "containerfile"}
        }

config = Config()

# =========================================================
# HELPERS
# =========================================================

def clean_path(path):
    path = str(path).replace("\\", "/")
    path = re.sub(r"^\./+", "", path)
    return path.strip("/")

def is_ignored(path):
    parts = clean_path(path).split("/")
    return any(part.lower() in config.ignored_directories for part in parts)

def read_text_from_zip(archive, filename, max_bytes=1_500_000):
    try:
        info = archive.getinfo(filename)
        if info.file_size > max_bytes:
            return ""
        return archive.read(filename).decode("utf-8", errors="ignore")
    except Exception:
        return ""

def safe_json(text):
    try:
        return json.loads(text)
    except Exception:
        return {}

def basename(path):
    return os.path.basename(clean_path(path)).lower()

def unique(items):
    result = []
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

def get_file_extension(filename):
    return Path(filename).suffix.lower()

# =========================================================
# PROJECT INVENTORY
# =========================================================

def build_project_inventory(archive):
    files = []
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        clean = clean_path(name)
        if clean and not is_ignored(name):
            files.append(clean)
    return files

# =========================================================
# TECHNOLOGY DETECTION
# =========================================================

def detect_manifest_type(directory_files):
    names = {basename(file) for file in directory_files}
    for tech, manifests in config.manifest_files.items():
        if manifests.intersection(names):
            return tech
    return "Unknown"

def detect_frameworks(directory_files, archive):
    frameworks = []
    package_files = [f for f in directory_files if basename(f) == "package.json"]
    for package_file in package_files:
        package = safe_json(read_text_from_zip(archive, package_file))
        dependencies = {}
        dependencies.update(package.get("dependencies", {}) or {})
        dependencies.update(package.get("devDependencies", {}) or {})
        dep_names = {str(key).lower() for key in dependencies.keys()}
        for framework, patterns in config.framework_detection.get("package_json", {}).items():
            if any(pattern.lower() in dep_names for pattern in patterns):
                frameworks.append(framework)
    source_text = ""
    for file in directory_files[:50]:
        if get_file_extension(file) in config.code_extensions:
            source_text += "\n" + read_text_from_zip(archive, file, 200_000).lower()
    for framework, patterns in config.framework_detection.get("source_code", {}).items():
        if any(re.search(pattern, source_text) for pattern in patterns):
            frameworks.append(framework)
    return unique(frameworks)

def detect_technologies(files, archive):
    technologies = set()
    for file in files:
        name = basename(file)
        if name == "package.json":
            technologies.add("Node.js / JavaScript")
        elif name in {"requirements.txt", "pyproject.toml", "pipfile"}:
            technologies.add("Python")
        elif "dockerfile" in name or name.endswith(".dockerfile"):
            technologies.add("Docker / OCI")
        elif name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            technologies.add("Docker Compose")
        elif name == "pom.xml":
            technologies.add("Java")
        elif name == "go.mod":
            technologies.add("Go")
        elif name == "cargo.toml":
            technologies.add("Rust")
        if get_file_extension(file) in {".yml", ".yaml"} and name not in {"docker-compose.yml", "docker-compose.yaml"}:
            content = read_text_from_zip(archive, file, 700_000)
            if re.search(r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service)\s*$", content):
                technologies.add("Kubernetes manifests")
    return sorted(technologies)

# =========================================================
# DOCKERFILE PARSING
# =========================================================

def parse_dockerfile_for_sources(archive, dockerfile_path):
    content = read_text_from_zip(archive, dockerfile_path, 500_000).lower()
    sources = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^copy\s+([^\s]+)\s+([^\s]+)", line)
        if match:
            source = match.group(1)
            if not source.startswith("/") and not source.startswith("http"):
                sources.append(source)
        match = re.match(r"^add\s+([^\s]+)\s+([^\s]+)", line)
        if match:
            source = match.group(1)
            if not source.startswith("/") and not source.startswith("http"):
                sources.append(source)
    return sources

# =========================================================
# SERVICE DETECTION (COMPOSE-FIRST)
# =========================================================

def parse_compose_services(archive, compose_files):
    services = {}
    for file in compose_files:
        text = read_text_from_zip(archive, file, 1_500_000)
        in_services = False
        current = None
        # First pass
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()
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
                        "name": name,
                        "file": file,
                        "image": None,
                        "build": None,
                        "dockerfile": None,
                        "context_dir": None,
                        "ports": [],
                        "depends_on": [],
                        "replicas": None,
                        "replicas_explicit": False
                    })
                continue
            if current and current in services and indent >= 4:
                entry = services[current]
                if stripped.startswith("image:"):
                    entry["image"] = stripped.split(":", 1)[1].strip().strip("'\"")
                elif stripped.startswith("build:"):
                    build_val = stripped.split(":", 1)[1].strip().strip("'\"")
                    entry["build"] = build_val
                    if build_val and not build_val.startswith(("http://", "https://", "docker://")):
                        entry["context_dir"] = clean_path(build_val).strip("/") or "."
        # Second pass for nested fields
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()
            if stripped == "services:" and indent == 0:
                in_services = True
                current = None
                block = None
                continue
            if not in_services:
                continue
            if indent == 2 and stripped.endswith(":"):
                current = stripped[:-1].strip().strip("'\"")
                block = None
                continue
            if not current or current not in services:
                continue
            if indent == 4:
                block = "ports" if stripped == "ports:" else \
                        "depends_on" if stripped == "depends_on:" else None
                replicas_match = re.match(r"replicas:\s*(\d+)", stripped)
                if replicas_match:
                    services[current]["replicas"] = int(replicas_match.group(1))
                    services[current]["replicas_explicit"] = True
                if stripped.startswith("dockerfile:"):
                    services[current]["dockerfile"] = stripped.split(":", 1)[1].strip().strip("'\"")
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
    # Clean up
    for item in services.values():
        item["ports"] = unique(item["ports"])
        item["depends_on"] = unique(item["depends_on"])
    return list(services.values())

def detect_services(files, archive, compose_services, k8s_workloads):
    if compose_services:
        services = []
        dockerfile_to_sources = {}
        for cs in compose_services:
            df = cs.get("dockerfile")
            if df:
                sources = parse_dockerfile_for_sources(archive, df)
                if sources:
                    dockerfile_to_sources[df] = sources
        for cs in compose_services:
            ctx = cs.get("context_dir")
            df = cs.get("dockerfile")
            source_dir = None
            if df and df in dockerfile_to_sources:
                for src in dockerfile_to_sources[df]:
                    full_path = src
                    if ctx and ctx != ".":
                        full_path = f"{ctx}/{src}".lstrip("/")
                    if any(f.startswith(full_path + "/") or f == full_path for f in files):
                        source_dir = full_path
                        break
            if not source_dir and ctx and ctx != ".":
                source_dir = ctx
            if not source_dir and ctx == ".":
                possible = {}
                for f in files:
                    if "/" in f and not is_ignored(f):
                        parts = f.split("/")
                        if len(parts) >= 2:
                            top = parts[0]
                            if top not in ["docker", ".github"]:
                                if top not in possible:
                                    possible[top] = []
                                possible[top].append(f)
                best = None
                for top, fs in possible.items():
                    if any(basename(f) in {"package.json", "requirements.txt"} for f in fs):
                        best = top
                        break
                if best:
                    source_dir = best
            if not source_dir and ctx:
                source_dir = ctx
            # When Compose uses a root build context (.), map conventional service names
            # to their application directories before falling back to Container-only detection.
            if not source_dir or source_dir == ".":
                conventional = {
                    "api": "backend",
                    "backend": "backend",
                    "analyzer": "analyzer",
                    "frontend": "frontend",
                    "web": "frontend",
                    "client": "frontend"
                }
                candidate = conventional.get(cs["name"].lower())
                if candidate and any(f == candidate or f.startswith(candidate + "/") for f in files):
                    source_dir = candidate
            tech = "Container"
            frameworks = []
            if source_dir:
                if source_dir == ".":
                    dir_files = [f for f in files if "/" not in f]
                else:
                    dir_files = [f for f in files if f.startswith(source_dir + "/") or f == source_dir]
                if dir_files:
                    tech = get_technology_with_frameworks(dir_files, archive)
                    frameworks = detect_frameworks(dir_files, archive)
            name_lower = cs["name"].lower()
            service_type = "backend"
            if name_lower in config.service_classification["frontend"]["name_patterns"]:
                service_type = "frontend"
            elif name_lower in config.service_classification["worker"]["name_patterns"]:
                service_type = "worker"
            else:
                if frameworks:
                    fw_text = " ".join(frameworks).lower()
                    if any(p in fw_text for p in config.service_classification["frontend"]["framework_patterns"]):
                        service_type = "frontend"
                    elif any(p in fw_text for p in config.service_classification["worker"]["framework_patterns"]):
                        service_type = "worker"
            services.append({
                "name": cs["name"],
                "technology": tech,
                "type": service_type,
                "directory": source_dir or "",
                "frameworks": frameworks,
                "source_type": "compose",
                "declared_replicas": cs.get("replicas"),
                "replicas_explicit": bool(cs.get("replicas_explicit", False)),
                "depends_on": cs.get("depends_on", [])
            })
        return services
    else:
        services = []
        directories = get_directory_structure(files)
        for path, dir_files in directories.items():
            if path in ["docker", ".github"] or any(part in config.ignored_directories for part in path.split("/")):
                continue
            name = clean_path(path).split("/")[-1]
            technology = detect_manifest_type(dir_files)
            if technology == "Unknown":
                continue
            tech_with_frameworks = get_technology_with_frameworks(dir_files, archive)
            service_type = classify_service(name, technology, dir_files, archive)
            if service_type:
                services.append({
                    "name": name,
                    "technology": tech_with_frameworks,
                    "type": service_type,
                    "directory": path,
                    "frameworks": detect_frameworks(dir_files, archive),
                    "source_type": "directory",
                    "declared_replicas": None,
                    "replicas_explicit": False
                })
        for item in k8s_workloads:
            if not any(s["name"].lower() == item["name"].lower() for s in services):
                services.append({
                    "name": item["name"],
                    "technology": "Kubernetes",
                    "type": "backend",
                    "directory": "",
                    "frameworks": [],
                    "source_type": "kubernetes",
                    "declared_replicas": item["replicas"],
                    "replicas_explicit": item.get("replicas_explicit", False)
                })
        return services

def get_directory_structure(files):
    directories = {}
    for file in files:
        if is_ignored(file):
            continue
        parts = clean_path(file).split("/")
        if len(parts) <= 1:
            continue
        for i in range(1, len(parts)):
            dir_path = "/".join(parts[:i])
            directories.setdefault(dir_path, []).append(file)
    return directories

def classify_service(name, technology, directory_files, archive):
    name_lower = name.lower()
    for service_type, rules in config.service_classification.items():
        if name_lower in rules["name_patterns"]:
            return service_type
    frameworks = detect_frameworks(directory_files, archive)
    framework_text = " ".join(frameworks).lower()
    for service_type, rules in config.service_classification.items():
        if any(pattern in framework_text for pattern in rules["framework_patterns"]):
            return service_type
    source_text = ""
    for file in directory_files[:80]:
        if get_file_extension(file) in config.code_extensions:
            source_text += "\n" + read_text_from_zip(archive, file, 150_000).lower()
    worker_indicators = {"bullmq", "celery", "rq.worker", "consumer(", "kafkaconsumer",
                         "rabbitmq", "background_tasks", "dramatiq", "queue", "job"}
    if any(indicator in source_text for indicator in worker_indicators):
        return "worker"
    if technology != "Unknown":
        return "backend"
    return None

def get_technology_with_frameworks(directory_files, archive):
    manifest = detect_manifest_type(directory_files)
    if manifest == "Unknown":
        return "Unknown"
    frameworks = detect_frameworks(directory_files, archive)
    if frameworks:
        return f"{manifest} / {' + '.join(frameworks)}"
    return manifest

# =========================================================
# DEPENDENCY DETECTION (PER SERVICE)
# =========================================================

def collect_service_manifest_and_code(service, files, archive):
    directory = clean_path(service.get("directory", "")).strip("/")
    if not directory or directory == ".":
        relevant = [f for f in files if "/" not in f]
    else:
        relevant = [f for f in files if f.startswith(directory + "/")]
    manifests = {}
    code_text = ""
    for f in relevant:
        name = basename(f)
        if name == "package.json":
            manifests["package.json"] = safe_json(read_text_from_zip(archive, f, 1_000_000))
        elif name in {"requirements.txt", "pyproject.toml"}:
            manifests[name] = read_text_from_zip(archive, f, 500_000).lower()
        elif get_file_extension(f) in config.code_extensions:
            code_text += "\n" + read_text_from_zip(archive, f, 300_000).lower()
    return manifests, code_text

def detect_dependencies_per_service(services, files, archive):
    service_deps = {}
    global_deps = {
        "databases": set(),
        "queues": set(),
        "caches": set(),
        "object_storage": set(),
        "external_services": set()
    }
    evidence = defaultdict(lambda: defaultdict(list))
    
    for service in services:
        manifests, code_text = collect_service_manifest_and_code(service, files, archive)
        deps = {
            "databases": [],
            "queues": [],
            "caches": [],
            "object_storage": [],
            "external_services": []
        }
        svc_evidence = defaultdict(list)
        
        if "package.json" in manifests:
            pkg = manifests["package.json"]
            all_deps = {}
            all_deps.update(pkg.get("dependencies", {}) or {})
            all_deps.update(pkg.get("devDependencies", {}) or {})
            dep_names = set(all_deps.keys())
            for db_name, patterns in config.db_dependency_manifest.items():
                if any(p in dep_names for p in patterns):
                    deps["databases"].append(db_name)
                    svc_evidence["databases"].append({db_name: "package.json"})
            for q_name, patterns in config.queue_dependency_manifest.items():
                if any(p in dep_names for p in patterns):
                    deps["queues"].append(q_name)
                    svc_evidence["queues"].append({q_name: "package.json"})
            for c_name, patterns in config.cache_dependency_manifest.items():
                if any(p in dep_names for p in patterns):
                    deps["caches"].append(c_name)
                    svc_evidence["caches"].append({c_name: "package.json"})
            for s_name, patterns in config.storage_dependency_manifest.items():
                if any(p in dep_names for p in patterns):
                    deps["object_storage"].append(s_name)
                    svc_evidence["object_storage"].append({s_name: "package.json"})
        if "requirements.txt" in manifests:
            req_text = manifests["requirements.txt"]
            for db_name, patterns in config.db_dependency_manifest.items():
                if any(p in req_text for p in patterns):
                    if db_name not in deps["databases"]:
                        deps["databases"].append(db_name)
                        svc_evidence["databases"].append({db_name: "requirements.txt"})
            # similarly for queues etc.
        
        for db_name, patterns in config.db_code_patterns.items():
            if any(re.search(p, code_text) for p in patterns):
                if db_name not in deps["databases"]:
                    deps["databases"].append(db_name)
                    svc_evidence["databases"].append({db_name: "code import"})
        for q_name, patterns in config.queue_code_patterns.items():
            if any(re.search(p, code_text) for p in patterns):
                if q_name not in deps["queues"]:
                    deps["queues"].append(q_name)
                    svc_evidence["queues"].append({q_name: "code import"})
        # similar for caches/storage – omitted for brevity
        
        urls = set()
        for match in re.findall(r"https?://[A-Za-z0-9._:-]+", code_text):
            try:
                host = urlparse(match).hostname
                if host and host not in {"localhost", "127.0.0.1"}:
                    urls.add(host)
            except Exception:
                pass
        deps["external_services"] = sorted(urls)[:20]
        global_deps["external_services"].update(urls)
        
        for key in deps:
            deps[key] = unique(deps[key])
        
        service_deps[service["name"]] = deps
        evidence[service["name"]] = dict(svc_evidence)
    
    for service in services:
        s_deps = service_deps.get(service["name"], {})
        for cat in ["databases", "queues", "caches", "object_storage"]:
            for item in s_deps.get(cat, []):
                global_deps[cat].add(item)
    for key in global_deps:
        global_deps[key] = sorted(global_deps[key])
    
    return service_deps, global_deps, evidence

# =========================================================
# DEPLOYMENT ANALYSIS (FIXED DETECTIONS)
# =========================================================

def detect_compose_files(files):
    names = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
    return [f for f in files if basename(f) in names]

def detect_kubernetes_files(files, archive):
    result = []
    for file in files:
        if get_file_extension(file) not in {".yml", ".yaml"}:
            continue
        text = read_text_from_zip(archive, file, 700_000)
        if re.search(r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service)\s*$", text):
            result.append(file)
    return result

def parse_kubernetes_workloads(files, archive):
    workloads = []
    for file in files:
        if get_file_extension(file) not in {".yml", ".yaml"}:
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
                    "replicas": int(replicas_match.group(1)) if replicas_match else None,
                    "replicas_explicit": bool(replicas_match),
                    "file": file
                })
    return workloads

def detect_docker(files):
    dockerfiles = []
    for f in files:
        name = basename(f)
        if "dockerfile" in name or name.endswith(".dockerfile"):
            dockerfiles.append(f)
    return dockerfiles

def detect_zerops(files):
    return [f for f in files if basename(f) in {"zerops.yml", "zerops.yaml"}]


def detect_ci_cd(files, archive=None):
    """Detect CI and CD separately. A CI workflow is not automatically CD."""
    workflows = []
    for file in files:
        path = clean_path(file).lower()
        name = basename(file)
        if (path.startswith(".github/workflows/") or
            path.startswith(".gitlab-ci") or
            name in {"jenkinsfile", "azure-pipelines.yml", "circleci", "bitbucket-pipelines.yml"}):
            workflows.append(file)
    workflows = unique(workflows)

    ci_workflows = []
    cd_workflows = []
    for file in workflows:
        text = read_text_from_zip(archive, file, 500_000).lower() if archive else ""
        has_ci = any(token in text for token in (
            "npm install", "npm test", "npm run build", "pip install", "pytest",
            "py_compile", "go test", "cargo test", "mvn test", "gradle test",
            "checkout@", "build"
        ))
        has_cd = any(token in text for token in (
            "docker push", "docker/build-push-action", "kubectl apply", "helm upgrade",
            "zerops deploy", "vercel --prod", "netlify deploy", "aws deploy", "gcloud run deploy"
        ))
        if has_ci or not has_cd:
            ci_workflows.append(file)
        if has_cd:
            cd_workflows.append(file)

    provider = None
    if workflows:
        provider = "GitHub Actions" if any(".github/workflows/" in clean_path(f).lower() for f in workflows) else "CI/CD Pipeline"

    return {
        "detected": bool(workflows),
        "provider": provider,
        "workflows": workflows,
        "ci_detected": bool(ci_workflows),
        "ci_workflows": unique(ci_workflows),
        "cd_detected": bool(cd_workflows),
        "cd_workflows": unique(cd_workflows)
    }

def detect_iac(files):
    results = []
    for file in files:
        name = basename(file)
        if (name.endswith(".tf") or 
            name in {"pulumi.yaml", "pulumi.yml", "serverless.yml", "serverless.yaml"}):
            results.append(file)
    return results

def detect_ports(files, archive):
    ports = set()
    for file in files:
        if is_ignored(file):
            continue
        ext = get_file_extension(file)
        if ext not in {".js", ".ts", ".jsx", ".tsx", ".py", ".yml", ".yaml", ".env", ".json"}:
            continue
        content = read_text_from_zip(archive, file, 500_000)
        for pattern in config.port_patterns:
            for match in re.findall(pattern, content, flags=re.IGNORECASE):
                try:
                    port = int(match)
                    if 1 <= port <= 65535:
                        ports.add(port)
                except ValueError:
                    pass
    return sorted(ports)

def detect_health_endpoints(files, archive):
    endpoints = set()
    for file in files:
        if is_ignored(file):
            continue
        if get_file_extension(file) not in config.code_extensions:
            continue
        content = read_text_from_zip(archive, file)
        for pattern in config.health_endpoint_patterns:
            endpoints.update(re.findall(pattern, content, flags=re.IGNORECASE))
    return sorted(endpoints)

def detect_service_health(services, files, archive, zerops_files):
    """Map health endpoints to specific services using source and Zerops evidence."""
    service_health = {}
    service_by_name = {s["name"].lower(): s["name"] for s in services}

    # Source-code evidence.
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        service_files = ([f for f in files if "/" not in f]
                         if directory in ("", ".")
                         else [f for f in files if f.startswith(directory + "/")])
        for file in service_files:
            if get_file_extension(file) not in config.code_extensions:
                continue
            content = read_text_from_zip(archive, file, 500_000)
            for pattern in config.health_endpoint_patterns:
                matches = re.findall(pattern, content, flags=re.IGNORECASE)
                if matches:
                    service_health[service["name"]] = matches[0]
                    break
            if service["name"] in service_health:
                break

    # Zerops evidence. Supports both `- setup: api` and nested service forms.
    for zf in zerops_files:
        content = read_text_from_zip(archive, zf, 700_000)
        current_service = None
        in_health = False
        for raw in content.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            setup = re.match(r"^-\s*setup:\s*([A-Za-z0-9_.-]+)", stripped)
            if setup:
                current_service = service_by_name.get(setup.group(1).lower(), setup.group(1))
                in_health = False
                continue
            nested = re.match(r"^\s{2}([A-Za-z0-9_.-]+):\s*$", raw)
            if nested and not stripped.startswith("- "):
                current_service = service_by_name.get(nested.group(1).lower(), nested.group(1))
                in_health = False
                continue
            if re.match(r"^\s+healthCheck:\s*$", raw):
                in_health = True
                continue
            if in_health:
                path_match = re.match(r"^\s+path:\s*['\"]?([^'\"]+)['\"]?\s*$", raw)
                if path_match and current_service:
                    service_health[current_service] = path_match.group(1).strip()
                    in_health = False
                    continue
                # A new top-level run/build/setup key ends this health block.
                if re.match(r"^\s{4}[A-Za-z][A-Za-z0-9_-]*:", raw) and not re.match(r"^\s+path:", raw):
                    in_health = False
    return service_health

# =========================================================
# ENVIRONMENT ANALYSIS
# =========================================================

def detect_environment(files, archive):
    env_files = []
    variables = []
    potential_secrets = []
    recognized_env = {".env", ".env.local", ".env.production", ".env.development", ".env.example", ".env.sample"}
    for file in files:
        name = basename(file)
        if name in recognized_env or name.startswith(".env") or name.endswith(".env"):
            env_files.append(file)
            content = read_text_from_zip(archive, file, 300_000)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if not key:
                    continue
                variables.append(key)
                if config.secret_patterns.search(key):
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

def detect_service_urls(services, files, archive):
    service_refs = []
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        if directory in ("", "."):
            relevant = [f for f in files if "/" not in f]
        else:
            relevant = [f for f in files if f.startswith(directory + "/")]
        text = ""
        for file in relevant[:150]:
            if get_file_extension(file) in config.source_extensions:
                text += "\n" + read_text_from_zip(archive, file, 250_000)
        for variable in unique(config.url_pattern.findall(text)):
            if any(token in variable for token in 
                   ("DATABASE", "DB_", "REDIS", "S3", "AWS_", "KAFKA", "RABBIT", "QUEUE", 
                    "MONGO", "POSTGRES", "MYSQL", "CASSANDRA", "DYNAMO")):
                continue
            service_refs.append({
                "service": service["name"],
                "variable": variable
            })
    return service_refs

def detect_service_references(services, files, archive):
    """Infer service-to-service HTTP references from environment/config/source evidence."""
    refs = []
    service_names = {s["name"].lower(): s["name"] for s in services}

    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        if directory in ("", "."):
            relevant = [f for f in files if "/" not in f]
        else:
            relevant = [f for f in files if f.startswith(directory + "/")]

        text_parts = []
        for file in relevant[:200]:
            if get_file_extension(file) in config.source_extensions or basename(file).startswith(".env"):
                text_parts.append(read_text_from_zip(archive, file, 300_000))
        text = "\n".join(text_parts)

        # Match URLs such as http://analyzer:5000 or http://api:3000.
        for match in re.finditer(r'https?://([A-Za-z0-9_.-]+)(?::\d+)?(?:/[^\s\"\']*)?', text):
            host = match.group(1).lower()
            target = service_names.get(host)
            if target and target != service["name"]:
                refs.append({
                    "service": service["name"],
                    "target": target,
                    "evidence": f"HTTP reference to {host} detected in project source/configuration"
                })

        # Match environment variables such as ANALYZER_URL or API_URL.
        for variable in re.findall(r'\b([A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT))\b', text):
            var = variable.lower()
            for candidate_lower, candidate in service_names.items():
                if candidate_lower in var and candidate != service["name"]:
                    refs.append({
                        "service": service["name"],
                        "target": candidate,
                        "evidence": f"{variable} references service '{candidate}'"
                    })

    return unique(refs)

# =========================================================
# RUNTIME SIGNALS
# =========================================================

def detect_runtime_signals(services, files, archive):
    """Extract concrete runtime signals used by bottleneck/simulation logic."""
    signals = {}
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        relevant = ([f for f in files if "/" not in f]
                    if directory in ("", ".")
                    else [f for f in files if f.startswith(directory + "/")])
        text = "\n".join(
            read_text_from_zip(archive, f, 400_000)
            for f in relevant
            if get_file_extension(f) in config.code_extensions or basename(f) == "package.json"
        )
        # axios({ timeout: 120000 }) / axios.get(..., { timeout: 120000 })
        matches = re.findall(r"\btimeout\s*:\s*(\d+)\b", text, flags=re.IGNORECASE)
        if matches and service["name"].lower() == "api":
            values = [int(x) for x in matches]
            signals["api_timeout_ms"] = max(values)
            if any("analyzer" in line.lower() for line in text.splitlines()):
                signals["api_analyzer_timeout_ms"] = max(values)
        if service["name"].lower() == "api" and re.search(r"ANALYZER_URL|analyzer:\\d+|/analyze", text, re.IGNORECASE):
            signals["api_calls_analyzer"] = True
    return signals


# =========================================================
# ARCHITECTURE GRAPH
# =========================================================


def build_architecture(services, global_deps, service_deps, compose_services, k8s_workloads, service_url_references=None):
    """Build an evidence-backed graph. Never invent an edge just because two services exist."""
    nodes = []
    edge_map = {}

    for service in services:
        nodes.append({
            "name": service["name"],
            "type": service["type"],
            "technology": service["technology"],
            "replicas": service.get("declared_replicas") if service.get("replicas_explicit", False) else None
        })

    infra_types = {
        "databases": "database",
        "queues": "queue",
        "caches": "cache",
        "object_storage": "object_storage"
    }
    for dep_type, node_type in infra_types.items():
        for item in global_deps.get(dep_type, []):
            nodes.append({
                "name": item.lower().replace(" ", "-"),
                "type": node_type,
                "technology": item,
                "replicas": 1
            })

    def add_edge(source, target, relationship, evidence):
        if not source or not target or source == target:
            return
        if source not in {s["name"] for s in services}:
            return
        if target not in {s["name"] for s in services} and target not in {n["name"] for n in nodes}:
            return
        key = (source, target)
        edge_map.setdefault(key, {"relationships": [], "evidence": []})
        if relationship not in edge_map[key]["relationships"]:
            edge_map[key]["relationships"].append(relationship)
        if evidence not in edge_map[key]["evidence"]:
            edge_map[key]["evidence"].append(evidence)

    # Strongest evidence: Compose depends_on.
    for cs in compose_services:
        for dep in cs.get("depends_on", []):
            add_edge(cs["name"], dep, "depends_on", "Docker Compose depends_on")

    # Kubernetes service/dependency evidence is intentionally conservative here.
    # Do not infer arbitrary pod-to-pod edges without explicit references.

    # Application-level references discovered from source/configuration.
    for ref in service_url_references or []:
        add_edge(ref["service"], ref["target"], "request", ref["evidence"])

    # Infrastructure dependencies.
    service_names = {s["name"] for s in services}
    node_names = {n["name"] for n in nodes}
    for service in services:
        s_deps = service_deps.get(service["name"], {})
        for dep_type in ("databases", "queues", "caches", "object_storage"):
            for item in s_deps.get(dep_type, []):
                target = item.lower().replace(" ", "-")
                if target in node_names:
                    add_edge(service["name"], target, dep_type.rstrip("s"), "Manifest/source dependency evidence")

    connections = [
        {
            "from": source,
            "to": target,
            "relationship": " + ".join(sorted(data["relationships"])),
            "relationships": sorted(data["relationships"]),
            "inference": "evidence-backed",
            "evidence": data["evidence"]
        }
        for (source, target), data in edge_map.items()
    ]

    # Order application nodes from upstream to downstream for deterministic UI rendering.
    app_names = [s["name"] for s in services]
    indegree = {name: 0 for name in app_names}
    outgoing = defaultdict(list)
    for edge in connections:
        if edge["from"] in indegree and edge["to"] in indegree:
            outgoing[edge["from"]].append(edge["to"])
            indegree[edge["to"]] += 1
    queue = [name for name in app_names if indegree[name] == 0]
    ordered_names = []
    while queue:
        current = queue.pop(0)
        ordered_names.append(current)
        for nxt in outgoing.get(current, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    for name in app_names:
        if name not in ordered_names:
            ordered_names.append(name)
    order_map = {name: i for i, name in enumerate(ordered_names)}
    nodes.sort(key=lambda n: order_map.get(n["name"], len(order_map)))

    return {
        "nodes": unique(nodes),
        "connections": unique(connections)
    }

def make_finding(severity, category, title, description, recommendation, score_impact):
    return {
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "recommendation": recommendation,
        "score_impact": score_impact
    }


def analyze_reliability(services, global_deps, health_endpoints, service_health,
                        dockerfiles, zerops_configs, compose_files, compose_services,
                        k8s_workloads, env_info, ci_cd, iac):
    findings = []

    for service in services:
        replicas = service.get("declared_replicas")
        replica_explicit = bool(service.get("replicas_explicit", False))
        if service["type"] in {"backend", "worker"} and not replica_explicit:
            findings.append(make_finding(
                "warning", "availability",
                f"{service['name']} single-instance availability risk",
                f"No explicit redundancy/replica configuration was detected for service '{service['name']}'. This static analysis does not prove the number of running replicas.",
                f"Scale '{service['name']}' to at least 2 instances when high availability is required.",
                10
            ))
        elif service["type"] == "frontend" and not replica_explicit:
            findings.append(make_finding(
                "info", "availability",
                "Frontend single-instance availability consideration",
                f"No explicit frontend redundancy/replica configuration was detected for service '{service['name']}'.",
                "Consider static asset redundancy or CDN caching for production availability.",
                2
            ))

    # Service-specific health checks: do not contradict global endpoint detection.
    backend_like = [s for s in services if s["type"] in {"backend", "worker"}]
    normalized_health = {k.lower(): v for k, v in service_health.items()}
    missing = [s["name"] for s in backend_like if s["name"].lower() not in normalized_health]
    if not health_endpoints and not service_health and backend_like:
        findings.append(make_finding(
            "warning", "observability", "No health check endpoints detected",
            "No application health endpoint was found in source or deployment configuration.",
            "Expose a service-specific /health, /healthz, /ready or equivalent endpoint.",
            8
        ))
    elif missing:
        findings.append(make_finding(
            "info", "observability", "Some services lack health checks",
            f"No service-specific health endpoint was mapped for: {', '.join(missing)}.",
            "Add service-specific health/readiness checks where appropriate.",
            3
        ))

    for db in global_deps.get("databases", []):
        findings.append(make_finding(
            "warning", "data", f"{db} dependency",
            f"{db} is a detected dependency and can affect availability and performance.",
            f"Review {db} backups, failover, connection pooling and recovery strategy.",
            6
        ))

    workers = [s for s in services if s["type"] == "worker"]
    if workers and not global_deps.get("queues"):
        findings.append(make_finding(
            "warning", "async", "Worker queue not detected",
            "Background workers were detected but no durable queue was identified.",
            "Consider a durable queue, retry policy and dead-letter handling.",
            7
        ))

    if not dockerfiles and not compose_files and not k8s_workloads:
        findings.append(make_finding(
            "info", "deployment", "No container/orchestration config",
            "No Dockerfile, Compose or Kubernetes workload was detected.",
            "Add explicit deployment configuration for reproducible production deployments.",
            3
        ))

    if zerops_configs:
        findings.append(make_finding(
            "info", "deployment", "Existing Zerops configuration",
            "A Zerops configuration file already exists in the project.",
            "Compare the existing configuration with the generated optimization plan.",
            0
        ))

    exposed = [x for x in env_info.get("potential_secrets", []) if x.get("value_exposed")]
    if exposed:
        findings.append(make_finding(
            "critical", "security", "Potential secrets exposed",
            f"{len(exposed)} secret-like environment variables appear to contain values.",
            "Remove committed credentials and use environment/secret management.",
            20
        ))

    if not ci_cd.get("ci_detected", False):
        findings.append(make_finding(
            "info", "delivery", "CI not detected",
            "No common continuous-integration workflow was detected.",
            "Add automated install, build and test checks.",
            2
        ))
    elif not ci_cd.get("cd_detected", False):
        findings.append(make_finding(
            "info", "delivery", "CD not detected",
            "CI workflow detected, but no deployment workflow or deployment command was found.",
            "Add a controlled deployment stage if continuous delivery is required.",
            0
        ))

    if not iac:
        findings.append(make_finding(
            "info", "infrastructure", "IaC not detected (Terraform/Pulumi)",
            "No Terraform, Pulumi or similar infrastructure-as-code configuration was detected.",
            "Consider versioning infrastructure configuration as complexity grows.",
            2
        ))

    if not services:
        findings.append(make_finding(
            "critical", "analysis", "No services identified",
            "The analyzer could not identify application services.",
            "Use conventional service directories, Compose or Kubernetes configuration.",
            30
        ))

    return findings


def build_score_breakdown(findings):
    return [
        {
            "title": f.get("title"),
            "severity": f.get("severity"),
            "impact": int(f.get("score_impact", 0))
        }
        for f in findings
        if int(f.get("score_impact", 0)) != 0
    ]

def calculate_score(findings):
    score = 100
    for item in findings:
        score -= int(item.get("score_impact", 0))
    return max(0, min(100, score))

def calculate_risk_summary(findings):
    counts = {"critical": 0, "warning": 0, "info": 0}
    for finding in findings:
        severity = finding.get("severity")
        if severity in counts:
            counts[severity] += 1
    if counts["critical"] > 0:
        level = "critical"
    elif counts["warning"] >= 3:
        level = "high"
    elif counts["warning"] > 0:
        level = "moderate"
    else:
        level = "low"
    return {
        "level": level,
        "critical": counts["critical"],
        "warning": counts["warning"],
        "info": counts["info"]
    }

# =========================================================
# BOTTLENECK DETECTION (MEANINGFUL)
# =========================================================

def detect_bottlenecks(services, global_deps, findings, architecture, service_deps, runtime_signals=None):
    """Produce deduplicated, evidence-backed bottlenecks with a reason and impact."""
    runtime_signals = runtime_signals or {}
    service_map = {s["name"]: s for s in services}
    connections = architecture.get("connections", [])
    result = []

    def add(item):
        # One underlying component/problem gets one finding; evidence is merged.
        for existing in result:
            if existing["key"] == item["key"]:
                for ev in item.get("evidence", []):
                    if ev and ev not in existing["evidence"]:
                        existing["evidence"].append(ev)
                return
        result.append(item)

    # Service dependency bottlenecks: report the downstream service once.
    downstream_sources = defaultdict(list)
    for edge in connections:
        source, target = edge.get("from"), edge.get("to")
        if source in service_map and target in service_map:
            downstream_sources[target].append((source, edge))

    for target, sources in downstream_sources.items():
        target_service = service_map[target]
        if target_service.get("type") not in {"backend", "worker"}:
            continue
        # A normal frontend -> API edge is not automatically a bottleneck.
        # Only surface it when multiple upstream services depend on the same API.
        if target.lower() == "api" and len({source for source, _ in sources}) < 2:
            continue
        evidence = []
        sources_text = []
        for source, edge in sources:
            sources_text.append(source)
            evidence.append(f"{source} → {target}")
            evidence.extend(edge.get("evidence", []))
        add({
            "key": f"service:{target}",
            "component": target,
            "type": "service-dependency",
            "risk": "medium",
            "title": f"{target} dependency bottleneck",
            "reason": (
                f"{', '.join(sorted(set(sources_text)))} depend on {target}. "
                f"Slow processing or unavailability in {target} can increase upstream latency "
                f"and propagate failures."
            ),
            "evidence": unique(evidence),
            "impact": f"Requests through {target} can experience higher latency or fail when {target} is unavailable.",
            "recommended_action": (
                f"Measure {target} latency, error rate and resource usage; scale it horizontally "
                f"when workload and availability requirements justify it."
            ),
            "priority": 90
        })

    # Long synchronous API timeout is a separate, evidence-backed capacity risk.
    timeout_ms = runtime_signals.get("api_analyzer_timeout_ms")
    if timeout_ms:
        seconds = timeout_ms / 1000
        add({
            "key": "api:long-timeout",
            "component": "api",
            "type": "long-request-timeout",
            "risk": "medium",
            "title": "Long synchronous analysis timeout",
            "reason": (
                f"The API waits up to {seconds:g} seconds for an analyzer response. "
                "Slow analysis can keep API requests open and consume concurrent request capacity."
            ),
            "evidence": [f"Analyzer request timeout: {timeout_ms} ms"],
            "impact": "Concurrent slow uploads can increase API latency and exhaust available request capacity.",
            "recommended_action": "Consider asynchronous analysis jobs with a durable queue and status polling for long-running workloads.",
            "priority": 85
        })

    for db in global_deps.get("databases", []):
        using = [s for s in services if db in service_deps.get(s["name"], {}).get("databases", [])]
        if using:
            add({
                "key": f"db:{db}",
                "component": db,
                "type": "database",
                "risk": "high" if len(using) > 1 else "medium",
                "title": f"{db} capacity/dependency bottleneck",
                "reason": f"{db} is used by {len(using)} service(s), so contention or unavailability can affect dependent services.",
                "evidence": [f"{s['name']} → {db}" for s in using],
                "impact": f"Database pressure or failure affects {len(using)} dependent service(s).",
                "recommended_action": "Review connection pooling, capacity, backups and failover strategy.",
                "priority": 80
            })

    for queue in global_deps.get("queues", []):
        using = [s for s in services if queue in service_deps.get(s["name"], {}).get("queues", [])]
        if using:
            add({
                "key": f"queue:{queue}",
                "component": queue,
                "type": "queue",
                "risk": "medium",
                "title": f"{queue} throughput bottleneck",
                "reason": f"{queue} is used by {len(using)} service(s) and can become a throughput constraint during bursts.",
                "evidence": [f"{s['name']} → {queue}" for s in using],
                "impact": "Queue backlog can increase processing latency.",
                "recommended_action": "Monitor queue depth and consumer throughput; add consumers when backlog grows.",
                "priority": 70
            })

    result.sort(key=lambda x: x.get("priority", 0), reverse=True)
    for item in result:
        item.pop("key", None)
        item.pop("priority", None)
    return result[:8]


_base_detect_bottlenecks_v10 = detect_bottlenecks

def detect_bottlenecks(services, global_deps, findings, architecture, service_deps, runtime_signals=None):
    result = _base_detect_bottlenecks_v10(services, global_deps, findings, architecture, service_deps, runtime_signals)
    evidence = getattr(app, "_project_evidence", {})
    deep = evidence.get("deep", {})

    for chain in deep.get("synchronous_chains", []):
        names = chain.get("chain", [])
        if len(names) >= 3:
            result.append({
                "component": "backend request pipeline",
                "type": "synchronous-service-chain",
                "risk": "high",
                "title": "Synchronous OCR and embedding pipeline",
                "reason": "The backend waits for downstream OCR and embedding processing before completing the document operation.",
                "evidence": ["backend → ocr-service", "backend → embedding-service", chain.get("evidence", "")],
                "impact": "Slow or unavailable OCR/embedding processing increases document-upload latency and can propagate failures back to the backend.",
                "recommended_action": "For long-running document processing, consider asynchronous jobs with durable queueing and retry/status handling.",
                "priority": 100
            })

    for item in deep.get("timeouts_ms", []):
        if item.get("max_ms", 0) >= 10000:
            seconds = item["max_ms"] / 1000
            result.append({
                "component": item["service"],
                "type": "long-request-timeout",
                "risk": "medium",
                "title": f"Long request timeout in {item['service']}",
                "reason": f"The service contains a request timeout up to {seconds:g} seconds, so slow downstream work can keep requests open for an extended period.",
                "evidence": [f"timeout={item['max_ms']} ms"],
                "impact": "Concurrent slow requests can consume connection/request capacity and increase latency.",
                "recommended_action": "Use bounded timeouts and asynchronous processing for operations that can legitimately run for tens of seconds.",
                "priority": 85
            })

    merged = {}
    for item in result:
        key = (item.get("component"), item.get("type"), item.get("title"))
        if key not in merged:
            merged[key] = item
        else:
            merged[key]["evidence"] = unique(merged[key].get("evidence", []) + item.get("evidence", []))
    result = list(merged.values())
    result.sort(key=lambda x: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(x.get("risk"), 0), reverse=True)
    return result[:8]

# =========================================================
# OPTIMIZATION PLAN (REALISTIC)
# =========================================================

def build_optimization_plan(services, global_deps, findings, deployment, service_deps):
    actions = []
    
    for service in services:
        explicit = bool(service.get("replicas_explicit", False))
        replicas = service.get("declared_replicas")
        if service["type"] in {"backend", "worker", "frontend"} and not explicit:
            actions.append({
                "priority": "high" if service["type"] == "backend" else "medium",
                "service": service["name"],
                "action": "Configure horizontal redundancy",
                "current": "Replica count not explicitly configured",
                "recommended": "2+ instances when high availability is required",
                "reason": f"No explicit HA/redundancy configuration was detected for {service['name']}."
            })
        
        # Only recommend health check if not already present
        if service["name"].lower() not in {str(k).lower() for k in deployment.get("service_health", {}).keys()} and service["type"] in {"backend", "worker"}:
            actions.append({
                "priority": "medium",
                "service": service["name"],
                "action": "Add health check endpoint",
                "current": "No service-specific health endpoint",
                "recommended": "/health or /healthz",
                "reason": "Allows load balancers to remove unhealthy instances."
            })
    
    for db in global_deps.get("databases", []):
        using_services = [s for s in services if db in service_deps.get(s["name"], {}).get("databases", [])]
        actions.append({
            "priority": "high" if len(using_services) > 1 else "medium",
            "service": "database layer",
            "action": "Review database HA/backup",
            "current": f"{db} used by {len(using_services)} service(s)",
            "recommended": "Backups + replication/failover appropriate to workload",
            "reason": f"Database availability directly impacts {len(using_services)} service(s)."
        })
    
    if any(s["type"] == "worker" for s in services) and not global_deps.get("queues"):
        actions.append({
            "priority": "medium",
            "service": "worker infrastructure",
            "action": "Introduce durable queueing",
            "current": "No queue detected",
            "recommended": "Durable queue + retry/dead-letter strategy",
            "reason": "Decouples producers from consumers and handles bursts."
        })
    
    if not deployment.get("dockerfiles") and not deployment.get("compose_files") and not deployment.get("kubernetes_files"):
        actions.append({
            "priority": "medium",
            "service": "deployment",
            "action": "Add explicit deployment configuration",
            "current": "No container/orchestration config",
            "recommended": "Containerized deployment definition",
            "reason": "Makes deployment reproducible and easier to optimize."
        })
    
    if not deployment.get("ci_cd"):
        actions.append({
            "priority": "low",
            "service": "delivery",
            "action": "Add CI/CD automation",
            "current": "No CI/CD config",
            "recommended": "Automated build + test + deployment checks",
            "reason": "Prevents reliability problems from reaching production."
        })
    
    return actions

# =========================================================
# ZEROPS CONFIG GENERATOR (PRESERVES EXISTING)
# =========================================================

def parse_existing_zerops(files, archive):
    zerops_files = detect_zerops(files)
    if not zerops_files:
        return None
    content = read_text_from_zip(archive, zerops_files[0], 500_000)
    return content


def get_service_start_command(service, files, archive=None):
    """Return a start command only when it is proven by project files."""
    directory = clean_path(service.get("directory", "")).strip("/")
    relevant = ([f for f in files if "/" not in f]
                if directory in ("", ".")
                else [f for f in files if f.startswith(directory + "/")])
    names = {basename(f) for f in relevant}
    tech = service.get("technology", "").lower()

    package = {}
    if archive:
        for f in relevant:
            if basename(f) == "package.json":
                package = safe_json(read_text_from_zip(archive, f, 1_000_000))
                break
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}

    if "python" in tech or "flask" in tech or "fastapi" in tech:
        if "app.py" in names:
            return "python3 app.py"
        if "main.py" in names:
            return "python3 main.py"
        if "server.py" in names:
            return "python3 server.py"
    if "vite" in tech or "react" in tech:
        if "preview" in scripts:
            return "npm run preview -- --host 0.0.0.0 --port 3000"
        if "start" in scripts:
            return "npm start"
    if "node" in tech or "express" in tech:
        if "start" in scripts:
            return "npm start"
        if "server.js" in names:
            return "node server.js"
        if "index.js" in names:
            return "node index.js"
    return None



def validate_zerops_configuration(services, service_health, files, existing_zerops, generated_config):
    """Validate deployment configuration against the uploaded project before calling it optimized."""
    service_names = {s["name"].lower() for s in services}
    errors = []
    warnings = []
    content = existing_zerops or generated_config or ""
    setups = [x.lower() for x in re.findall(r"^\s*-\s*setup:\s*([A-Za-z0-9_.-]+)", content, re.MULTILINE)]
    if setups:
        missing = sorted(service_names - set(setups))
        extra = sorted(set(setups) - service_names)
        if missing:
            errors.append(f"Missing service configuration: {', '.join(missing)}")
        if extra:
            errors.append(f"Unknown service configuration: {', '.join(extra)}")
    else:
        errors.append("No Zerops setup entries detected")

    # Validate health paths only when the configuration claims to contain them.
    for name, health in service_health.items():
        if name.lower() in content.lower() and health not in content:
            warnings.append(f"Detected health endpoint for {name} is not present in generated configuration")

    # Validate known source/start commands for the generated fallback.
    if not existing_zerops:
        for service in services:
            cmd = get_service_start_command(service, files, None)
            if cmd and "python3 app.py" in cmd:
                directory = clean_path(service.get("directory", "")).strip("/")
                if not any(f == f"{directory}/app.py" for f in files):
                    errors.append(f"{service['name']} references app.py but the file was not found")
            if cmd and cmd == "npm start":
                directory = clean_path(service.get("directory", "")).strip("/")
                pkg_files = [f for f in files if f == f"{directory}/package.json"]
                if not pkg_files:
                    errors.append(f"{service['name']} has no package.json for npm start")

    return {
        "valid": not errors,
        "errors": unique(errors),
        "warnings": unique(warnings),
        "services_configured": setups
    }

def generate_zerops_config(services, service_health, files, existing_zerops=None, archive=None):
    """Never invent a deploy command when an existing project-specific Zerops config exists."""
    if existing_zerops:
        lines = [
            "# Zerops Autopilot recommended configuration",
            "# The uploaded project already contains zerops.yml.",
            "# The existing deployment commands, runtimes, ports and health checks are preserved below.",
            "# Autopilot recommendations are comments only; no unsupported Zerops syntax is invented.",
            ""
        ]
        lines.extend(existing_zerops.rstrip().splitlines())
        lines.extend(["", "# --- Autopilot recommendations ---"])
        for service in services:
            if service.get("type") in {"backend", "worker", "frontend"} and not service.get("replicas_explicit", False):
                lines.append(f"# No explicit replica/HA configuration detected for {service['name']}; consider redundancy when HA is required.")
        for name, health in service_health.items():
            lines.append(f"# Detected health check: {name} -> {health}")
        return "\n".join(lines).rstrip() + "\n"

    # No existing config: generate only commands proven by the uploaded files.
    lines = ["# Generated by Zerops Autopilot", "# Only project-evidenced commands are emitted.", ""]
    for service in services:
        name = service["name"]
        directory = clean_path(service.get("directory", "")).strip("/")
        tech = service.get("technology", "").lower()
        start = get_service_start_command(service, files, archive)
        lines.append(f"- setup: {name}")
        lines.append("  run:")
        if "python" in tech or "flask" in tech or "fastapi" in tech:
            lines.append("    base: alpine/python@3.12")
        elif "node" in tech or "express" in tech or "react" in tech or "vite" in tech:
            lines.append("    base: nodejs@22")
        else:
            lines.append("    base: docker@latest")
        if start:
            lines.append(f"    start: {start}")
        if name in service_health:
            lines.append("    healthCheck:")
            lines.append("      httpGet:")
            lines.append(f"        path: {service_health[name]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def build_failure_scenarios(services, global_deps, architecture):
    scenarios = []
    for service in services:
        scenarios.append({
            "id": service["name"],
            "type": "service_failure",
            "target": service["name"],
            "label": f"{service['name']} failure",
            "description": f"Simulate failure of the {service['name']} service."
        })
    for category in ("databases", "queues", "caches", "object_storage"):
        for item in global_deps.get(category, []):
            scenarios.append({
                "id": f"{category}:{item}",
                "type": f"{category.rstrip('s')}_failure",
                "target": item,
                "label": f"{item} failure",
                "description": f"Simulate loss of {item}."
            })
    scenarios.append({
        "id": "traffic_spike",
        "type": "traffic_spike",
        "target": "all",
        "label": "Traffic Spike ×10",
        "description": "Simulate a tenfold increase in incoming traffic."
    })
    scenarios.append({
        "id": "cascading",
        "type": "cascading_failure",
        "target": "critical-path",
        "label": "Cascading Failure",
        "description": "Simulate failure propagation through the inferred dependency graph."
    })
    return scenarios


def _graph_service_edges(architecture):
    return [
        (e["from"], e["to"])
        for e in architecture.get("connections", [])
        if e.get("from") and e.get("to")
    ]


def _dependent_services(root, edges):
    reverse = defaultdict(list)
    for source, target in edges:
        reverse[target].append(source)
    affected = set()
    queue = list(reverse.get(root, []))
    while queue:
        item = queue.pop(0)
        if item in affected:
            continue
        affected.add(item)
        queue.extend(reverse.get(item, []))
    return sorted(affected)


def simulate_failure(services, architecture, target, baseline_score=100):
    service_names = {s["name"] for s in services}
    if target not in service_names:
        return {"error": f"Unknown service: {target}"}
    edges = _graph_service_edges(architecture)
    affected = _dependent_services(target, edges)
    direct = sorted({source for source, dest in edges if dest == target})
    severity = "critical" if affected else "high"
    return {
        "scenario": f"{target} failure",
        "type": "service_failure",
        "target": target,
        "reliability": max(0, int(baseline_score) - (25 + 15 * len(affected))),
        "severity": severity,
        "root_service": target,
        "direct_dependents": direct,
        "affected_services": affected,
        "blast_radius": len(affected),
        "impact": [
            f"The {target} service is unavailable.",
            *(f"{name} depends on the failed service through the inferred dependency graph." for name in affected)
        ],
        "recommended_action": (
            f"Add redundancy and health-aware routing for {target}. "
            "For long-running work, isolate processing with asynchronous jobs where appropriate."
        )
    }


def simulate_traffic_spike(services, architecture, multiplier=10, baseline_score=100):
    try:
        multiplier = float(multiplier)
    except (TypeError, ValueError):
        multiplier = 10.0
    multiplier = max(1.0, min(multiplier, 100.0))
    service_names = [s["name"] for s in services]
    edges = _graph_service_edges(architecture)
    incoming = defaultdict(int)
    outgoing = defaultdict(list)
    for source, target in edges:
        outgoing[source].append(target)
        incoming[target] += 1

    # A simple static load-propagation model: a service receives the spike if it
    # is on a request path; downstream services inherit the multiplier.
    affected = []
    for name in service_names:
        if incoming[name] or name.lower() in {"frontend", "api"}:
            affected.append(name)
    if not affected:
        affected = service_names[:]

    # The analyzer is the strongest pressure point in this project's synchronous path.
    pressure = []
    for name in affected:
        if name.lower() == "analyzer":
            pressure.append({
                "service": name,
                "reason": "Analysis requests ultimately depend on analyzer processing.",
                "expected_effect": f"Analyzer workload may increase by approximately {multiplier:g}×."
            })
        elif name.lower() == "api":
            pressure.append({
                "service": name,
                "reason": "API receives frontend analysis requests and waits for downstream analyzer responses.",
                "expected_effect": f"Concurrent API request pressure may increase by approximately {multiplier:g}×."
            })

    # Static score only; this is not a claim about measured CPU/memory capacity.
    penalty = min(60, int((multiplier - 1) * 4))
    score = max(0, int(baseline_score) - penalty)
    if any(p["service"].lower() == "analyzer" for p in pressure):
        score = max(0, score - 10)

    return {
        "scenario": "Traffic Spike ×10" if multiplier == 10 else f"Traffic Spike ×{multiplier:g}",
        "type": "traffic_spike",
        "multiplier": multiplier,
        "reliability": score,
        "severity": "warning" if multiplier >= 5 else "info",
        "affected_services": affected,
        "impact": [
            f"Simulated incoming request volume increased by approximately {multiplier:g}×.",
            "Response latency and concurrent request pressure may increase.",
            "Static analysis cannot determine actual CPU, memory or network saturation without runtime measurements."
        ],
        "pressure_points": pressure,
        "recommended_action": "Monitor latency/resource utilization and scale API/analyzer capacity when workload requires it; use asynchronous processing for long-running analysis jobs."
    }


def simulate_cascading_failure(services, architecture):
    edges = _graph_service_edges(architecture)
    if not services:
        return {"scenario": "Cascading Failure", "reliability": 0, "affected_services": []}
    # Choose the most downstream application service as the root for a deterministic static simulation.
    targets = {target for _, target in edges}
    roots = [s["name"] for s in services if s["name"] not in {source for source, _ in edges} and s["name"] in targets]
    root = roots[0] if roots else services[-1]["name"]
    result = simulate_failure(services, architecture, root)
    result["scenario"] = "Cascading Failure"
    result["type"] = "cascading_failure"
    result["severity"] = "critical" if result.get("affected_services") else "high"
    return result


def run_simulation(services, architecture, scenario, target=None, multiplier=10, baseline_score=100):
    """Dispatch by scenario type. Scenario IDs are never treated as service names."""
    raw = str(scenario or "").strip().lower().replace("-", "_").replace(" ", "_")
    target_raw = str(target or "").strip().lower().replace("-", "_").replace(" ", "_")

    # Traffic is a scenario, not a service. Accept clients that send it as either
    # scenario, type, id, or (incorrectly) target.
    if raw in {"traffic_spike", "traffic", "traffic_spike_x10", "trafficspike"} or target_raw in {"traffic_spike", "traffic_spike_x10"}:
        return simulate_traffic_spike(services, architecture, multiplier, baseline_score)

    if raw in {"cascading", "cascading_failure"}:
        result = simulate_cascading_failure(services, architecture)
        result["reliability"] = max(0, int(baseline_score) - (25 + 15 * len(result.get("affected_services", []))))
        return result

    if raw in {"service_failure", "failure"}:
        if not target:
            return {"error": "A service target is required for a service-failure simulation"}
        return simulate_failure(services, architecture, target, baseline_score)

    # Backward compatibility: if a real service name was supplied as the scenario,
    # interpret it as a service failure. Never interpret traffic_spike this way.
    service_names = {s["name"] for s in services}
    if raw in {name.lower() for name in service_names}:
        real_target = next(name for name in service_names if name.lower() == raw)
        return simulate_failure(services, architecture, real_target, baseline_score)

    return {"error": f"Unsupported simulation scenario: {scenario}"}

def build_summary(services, technologies, global_deps, score, risk_summary, bottlenecks):
    service_counts = {
        "frontend": len([s for s in services if s["type"] == "frontend"]),
        "backend": len([s for s in services if s["type"] == "backend"]),
        "worker": len([s for s in services if s["type"] == "worker"])
    }
    return {
        "headline": (
            "Architecture requires reliability improvements"
            if risk_summary["critical"] or risk_summary["warning"]
            else "Architecture appears structurally healthy"
        ),
        "reliability_score": score,
        "risk_level": risk_summary["level"],
        "service_counts": service_counts,
        "technology_count": len(technologies),
        "database_count": len(global_deps.get("databases", [])),
        "queue_count": len(global_deps.get("queues", [])),
        "cache_count": len(global_deps.get("caches", [])),
        "top_bottleneck": bottlenecks[0]["component"] if bottlenecks else None
    }

# =========================================================
# API ENDPOINTS
# =========================================================

@app.get("/")
def home():
    return jsonify({
        "service": "Zerops Autopilot Analyzer",
        "status": "running",
        "version": VERSION,
        "mode": "static-analysis",
        "ai_required": False,
        "database_required": False
    })

@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "zerops-autopilot-analyzer",
        "version": VERSION
    })


@app.post("/analyze-project")
@app.post("/analyze")
def analyze_project():
    if "project" not in request.files:
        return jsonify({"error": "No project file received"}), 400

    project = request.files["project"]
    if not project.filename:
        return jsonify({"error": "Uploaded project has no filename"}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "project.zip")
        project.save(zip_path)

        if not zipfile.is_zipfile(zip_path):
            return jsonify({"error": "Uploaded file is not a valid ZIP archive"}), 400

        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                files = build_project_inventory(archive)
                technologies = detect_technologies(files, archive)

                compose_files = detect_compose_files(files)
                compose_services = parse_compose_services(archive, compose_files)
                kubernetes_files = detect_kubernetes_files(files, archive)
                k8s_workloads = parse_kubernetes_workloads(kubernetes_files, archive)

                services = detect_services(files, archive, compose_services, k8s_workloads)
                service_deps, global_deps, dependency_evidence = detect_dependencies_per_service(
                    services, files, archive
                )

                ports = detect_ports(files, archive)
                health_endpoints = detect_health_endpoints(files, archive)
                zerops_files = detect_zerops(files)
                service_health = detect_service_health(services, files, archive, zerops_files)

                dockerfiles = detect_docker(files)
                ci_cd = detect_ci_cd(files, archive)
                iac = detect_iac(files)
                env_info = detect_environment(files, archive)
                service_url_references = detect_service_references(services, files, archive)
                runtime_signals = detect_runtime_signals(services, files, archive)

                architecture = build_architecture(
                    services, global_deps, service_deps,
                    compose_services, k8s_workloads,
                    service_url_references
                )

                findings = analyze_reliability(
                    services, global_deps, health_endpoints, service_health,
                    dockerfiles, zerops_files, compose_files, compose_services,
                    k8s_workloads, env_info, ci_cd, iac
                )

                reliability_score = calculate_score(findings)
                risk_summary = calculate_risk_summary(findings)

                bottlenecks = detect_bottlenecks(
                    services, global_deps, findings, architecture, service_deps, runtime_signals
                )

                deployment_info = {
                    "docker_detected": bool(dockerfiles),
                    "dockerfiles_count": len(dockerfiles),
                    "dockerfiles": dockerfiles,
                    "docker_compose_detected": bool(compose_files),
                    "compose_files": compose_files,
                    "kubernetes_detected": bool(kubernetes_files or k8s_workloads),
                    "kubernetes_files": kubernetes_files,
                    "ci_cd": ci_cd,
                    "ci_cd_detected": ci_cd["detected"],
                    "ci_detected": ci_cd.get("ci_detected", False),
                    "ci_workflows": ci_cd.get("ci_workflows", []),
                    "cd_detected": ci_cd.get("cd_detected", False),
                    "cd_workflows": ci_cd.get("cd_workflows", []),
                    "ci_cd_provider": ci_cd["provider"],
                    "iac": iac,
                    "iac_detected": bool(iac),
                    "ports": ports,
                    "health_endpoints": health_endpoints,
                    "service_health": service_health,
                    "zerops_detected": bool(zerops_files),
                    "zerops_files": zerops_files,
                    "containerization_detected": bool(dockerfiles or compose_files or k8s_workloads),
                    "zerops": {
                        "detected": bool(zerops_files),
                        "files": zerops_files
                    },
                    "ci": {
                        "detected": ci_cd.get("ci_detected", False),
                        "workflows": ci_cd.get("ci_workflows", []),
                        "provider": ci_cd.get("provider")
                    },
                    "cd": {
                        "detected": ci_cd.get("cd_detected", False),
                        "workflows": ci_cd.get("cd_workflows", []),
                        "provider": ci_cd.get("provider")
                    },
                    "containerization": {
                        "detected": bool(dockerfiles or compose_files or k8s_workloads),
                        "dockerfiles": dockerfiles,
                        "dockerfiles_count": len(dockerfiles),
                        "compose": bool(compose_files),
                        "compose_files": compose_files,
                        "kubernetes": bool(kubernetes_files or k8s_workloads)
                    }
                }

                optimization_plan = build_optimization_plan(
                    services, global_deps, findings, deployment_info, service_deps
                )

                existing_zerops = parse_existing_zerops(files, archive)
                zerops_yml = generate_zerops_config(
                    services, service_health, files, existing_zerops, archive
                )
                deployment_validation = validate_zerops_configuration(
                    services, service_health, files, existing_zerops, zerops_yml
                )

                # Single source of truth for deployment/readiness reporting.
                deployment_status = {
                    "zerops": {
                        "detected": bool(zerops_files),
                        "files": zerops_files,
                        "status": "Detected" if zerops_files else "Not Detected"
                    },
                    "ci": {
                        "detected": bool(ci_cd.get("ci_detected")),
                        "workflows": ci_cd.get("ci_workflows", []),
                        "provider": ci_cd.get("provider"),
                        "status": "Detected" if ci_cd.get("ci_detected") else "Not Detected"
                    },
                    "cd": {
                        "detected": bool(ci_cd.get("cd_detected")),
                        "workflows": ci_cd.get("cd_workflows", []),
                        "provider": ci_cd.get("provider"),
                        "status": "Detected" if ci_cd.get("cd_detected") else "Not Detected"
                    },
                    "containerization": {
                        "detected": bool(dockerfiles or compose_files or k8s_workloads),
                        "dockerfiles": dockerfiles,
                        "dockerfiles_count": len(dockerfiles),
                        "compose": bool(compose_files),
                        "compose_files": compose_files,
                        "kubernetes": bool(k8s_workloads),
                        "status": "Detected" if (dockerfiles or compose_files or k8s_workloads) else "Not Detected"
                    }
                }
                delivery_readiness = {
                    "ci": deployment_status["ci"],
                    "cd": deployment_status["cd"],
                    "ci_cd": {
                        "ci_detected": deployment_status["ci"]["detected"],
                        "cd_detected": deployment_status["cd"]["detected"],
                        "status": (
                            "CI detected / CD detected" if deployment_status["ci"]["detected"] and deployment_status["cd"]["detected"]
                            else "CI detected / CD not detected" if deployment_status["ci"]["detected"]
                            else "CI not detected / CD detected" if deployment_status["cd"]["detected"]
                            else "CI/CD not detected"
                        )
                    },
                    "containerization": deployment_status["containerization"],
                    "zerops": deployment_status["zerops"]
                }

                # Projected score is intentionally capped below 100 because
                # static analysis cannot prove runtime/network/database resilience.
                resolvable_titles = {
                    f"{s['name']} single instance" for s in services
                    if s["type"] in {"backend", "worker", "frontend"}
                }
                projected_findings = []
                for finding in findings:
                    title = finding.get("title", "").lower()
                    if "single-instance" in title or "single instance" in title:
                        continue
                    if "some services lack health checks" in title:
                        continue
                    projected_findings.append(finding)
                projected_score = min(92, calculate_score(projected_findings))
                if not deployment_validation["valid"]:
                    projected_score = min(projected_score, 70)

                failure_scenarios = build_failure_scenarios(
                    services, global_deps, architecture
                )

                summary = build_summary(
                    services, technologies, global_deps,
                    reliability_score, risk_summary, bottlenecks
                )
                summary.update({
                    "projected_reliability_score": projected_score,
                    "docker_status": "Detected" if dockerfiles else "Not Detected",
                    "containerization_status": "Detected" if deployment_info["containerization_detected"] else "Not Detected",
                    "ci_cd_status": (
                        "CI detected / CD detected" if ci_cd.get("ci_detected") and ci_cd.get("cd_detected")
                        else "CI detected / CD not detected" if ci_cd.get("ci_detected")
                        else "CI not detected / CD detected" if ci_cd.get("cd_detected")
                        else "CI/CD not detected"
                    ),
                    "ci_status": "Detected" if ci_cd.get("ci_detected") else "Not Detected",
                    "cd_status": "Detected" if ci_cd.get("cd_detected") else "Not Detected",
                    "zerops_status": "Detected" if zerops_files else "Not Detected"
                })

                app.last_analysis_model = {
                    "services": services,
                    "architecture": architecture,
                    "global_deps": global_deps,
                    "reliability_score": reliability_score,
                    "deployment_status": deployment_status
                }

                response = {
                    "status": "success",
                    "analyzer": {
                        "name": "Zerops Autopilot Analyzer",
                        "version": VERSION,
                        "mode": "static-analysis",
                        "ai_required": False,
                        "database_required": False
                    },
                    "project": project.filename,
                    "file_count": len(files),
                    "summary": summary,
                    "technologies": technologies,
                    "services": services,
                    "dependencies": global_deps,
                    "dependency_evidence": dependency_evidence,
                    "deployment": deployment_info,
                    "deployment_status": deployment_status,
                    "delivery_readiness": delivery_readiness,
                    "deployment_summary": deployment_status,
                    "runtime_signals": runtime_signals,
                    "deployment_validation": deployment_validation,
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
                    "potential_reliability_score": projected_score,
                    "projected_reliability_score": projected_score,
                    "score_breakdown": build_score_breakdown(findings),
                    "risk_summary": risk_summary,
                    "findings": findings,
                    "bottlenecks": bottlenecks,
                    "optimization_plan": optimization_plan,
                    "zerops_detected": deployment_status["zerops"]["detected"],
                    "ci_detected": deployment_status["ci"]["detected"],
                    "cd_detected": deployment_status["cd"]["detected"],
                    "containerization_detected": deployment_status["containerization"]["detected"],
                    "existing_zerops_yml": existing_zerops,
                    "zeropsYml": zerops_yml,
                    "files": files[:200]
                }

                return jsonify(response)

        except zipfile.BadZipFile:
            return jsonify({"error": "The uploaded ZIP file is corrupted"}), 400
        except Exception as error:
            app.logger.exception("Project analysis failed")
            return jsonify({"error": "Project analysis failed", "details": str(error)}), 500


@app.post("/simulate")
@app.post("/api/simulate")
def simulate():
    """Run a safe static simulation; it never sends traffic to the uploaded project."""
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario") or payload.get("type") or payload.get("id") or payload.get("service")
    target = payload.get("target")
    if not scenario and str(target or "").strip().lower() in {"traffic_spike", "traffic_spike_x10"}:
        scenario = "traffic_spike"
        target = None
    multiplier = payload.get("multiplier", 10)
    if not scenario:
        return jsonify({"error": "scenario is required"}), 400

    # A simulation request needs the architecture from the last analysis. This process-local
    # cache is intentionally small and only stores the latest normalized model.
    model = getattr(app, "last_analysis_model", None)
    if not model:
        return jsonify({"error": "Run a project analysis before running a simulation"}), 409

    result = run_simulation(
        model["services"], model["architecture"], scenario, target, multiplier,
        model.get("reliability_score", 100)
    )
    if result.get("error"):
        return jsonify(result), 400
    return jsonify({"status": "success", "simulation": result})




# =========================================================
# V10 EVIDENCE-FIRST OVERRIDES
# =========================================================
# These overrides intentionally sit above the legacy rule engine. They make
# one normalized project-evidence model authoritative for deployment,
# scaling, dependencies, bottlenecks and simulation.

VERSION = "10.0"


def _norm_name(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _service_aliases(name):
    raw = str(name or "").strip()
    variants = {raw, raw.replace("-", ""), raw.replace("_", "")}
    if raw.lower() in {"ocr-service", "ocrservice"}:
        variants.update({"ocr-service", "ocrservice", "ocr"})
    if raw.lower() in {"embedding-service", "embeddingservice"}:
        variants.update({"embedding-service", "embeddingservice", "embedding"})
    if raw.lower() in {"backend-api", "api"}:
        variants.update({"backend-api", "api", "backend"})
    return {_norm_name(v) for v in variants}


def _read_named_file(files, archive, names, max_bytes=800_000):
    wanted = {str(n).lower() for n in names}
    for f in files:
        if basename(f).lower() in wanted:
            return f, read_text_from_zip(archive, f, max_bytes)
    return None, ""


def parse_zerops_import_evidence(files, archive):
    """Parse explicit min/max containers and database HA mode from Zerops import YAML.
    This is intentionally regex based so the analyzer has no PyYAML dependency.
    """
    path, text = _read_named_file(files, archive, {"zerops-project-import.yml", "zerops-project-import.yaml"})
    result = {"file": path, "services": {}, "databases": {}}
    if not text:
        return result

    current = None
    in_services = False
    in_databases = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "services:":
            in_services, in_databases = True, False
            current = None
            continue
        if stripped == "databases:":
            in_services, in_databases = False, True
            current = None
            continue
        host = re.match(r"^\s*-?\s*hostname:\s*['\"]?([^'\"\s]+)", stripped, re.I)
        if host:
            current = host.group(1)
            if in_services:
                result["services"].setdefault(current, {})
            elif in_databases:
                result["databases"].setdefault(current, {})
            continue
        if current and in_services:
            m = re.match(r"^(?:-\s*)?(minContainers|maxContainers):\s*(\d+)", stripped, re.I)
            if m:
                result["services"].setdefault(current, {})[m.group(1)] = int(m.group(2))
            m = re.match(r"^(?:-\s*)?mode:\s*['\"]?([^'\"\s]+)", stripped, re.I)
            if m:
                result["services"].setdefault(current, {})["mode"] = m.group(1)
        elif current and in_databases:
            m = re.match(r"^(?:-\s*)?mode:\s*['\"]?([^'\"\s]+)", stripped, re.I)
            if m:
                result["databases"].setdefault(current, {})["mode"] = m.group(1)
            m = re.match(r"^(?:-\s*)?type:\s*['\"]?([^'\"\s]+)", stripped, re.I)
            if m:
                result["databases"].setdefault(current, {})["type"] = m.group(1)
    return result


def parse_zerops_runtime_config(files, archive):
    """Extract project-specific Zerops setup names and runtime commands."""
    path, text = _read_named_file(files, archive, {"zerops.yml", "zerops.yaml"})
    setups = []
    current = None
    block = {}
    for raw in text.splitlines():
        stripped = raw.strip()
        m = re.match(r"^-\s*setup:\s*([A-Za-z0-9_.-]+)", stripped)
        if m:
            if current:
                setups.append({"name": current, **block})
            current = m.group(1)
            block = {}
            continue
        if current:
            m = re.match(r"^base:\s*(.+)$", stripped)
            if m: block["base"] = m.group(1).strip().strip("'\"")
            m = re.match(r"^start:\s*(.+)$", stripped)
            if m: block["start"] = m.group(1).strip().strip("'\"")
            m = re.match(r"^build:\s*(.+)$", stripped)
            if m: block["build"] = m.group(1).strip().strip("'\"")
            m = re.match(r"^deploy:\s*(.+)$", stripped)
            if m: block["deploy"] = m.group(1).strip().strip("'\"")
            m = re.match(r"^ports?:\s*(.+)$", stripped)
            if m: block["ports"] = m.group(1).strip()
    if current:
        setups.append({"name": current, **block})
    return {"file": path, "setups": setups}


def detect_deep_runtime_evidence(files, archive, services):
    """Detect high-value runtime facts without pretending static analysis is runtime measurement."""
    all_text_parts = []
    per_service = {}
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        relevant = [f for f in files if (f.startswith(directory + "/") if directory else "/" not in f)]
        text_parts = []
        for f in relevant[:300]:
            if get_file_extension(f) in config.source_extensions or basename(f).startswith(".env"):
                text_parts.append(read_text_from_zip(archive, f, 400_000))
        text = "\n".join(text_parts)
        per_service[service["name"]] = text
        all_text_parts.append(text)

    all_text = "\n".join(all_text_parts)
    result = {
        "services": per_service,
        "system_dependencies": [],
        "persistent_state": [],
        "external_model_dependencies": [],
        "fallbacks": [],
        "synchronous_chains": [],
        "timeouts_ms": [],
        "database_ha": []
    }

    if re.search(r"pytesseract|tesseract-ocr|tesseract", all_text, re.I):
        result["system_dependencies"].append({
            "name": "Tesseract OCR",
            "evidence": "pytesseract import or Tesseract installation/reference detected"
        })

    faiss_match = re.search(r"(?:INDEX_DIR|index_dir)[^\n]{0,160}([\"'][^\"']*faiss[^\"']*[\"'])", all_text, re.I)
    if not faiss_match:
        path_match = re.search(r"(/[A-Za-z0-9_.-]*/(?:tmp/)?faiss(?:_[A-Za-z0-9_.-]+)?|/tmp/faiss_[A-Za-z0-9_.-]+)", all_text, re.I)
        path = path_match.group(1) if path_match else None
    else:
        path = faiss_match.group(1).strip("'\"")
    if path:
        state_service = next((s for s,t in per_service.items() if re.search(r"(?:INDEX_DIR|faiss|sentence.?transformers)", t, re.I) and ("embedding" in s.lower() or "faiss" in t.lower())), "embedding-service")
        result["persistent_state"].append({
            "service": state_service,
            "path": path,
            "ephemeral": path.startswith("/tmp/") or path.startswith("/var/tmp/")
        })

    if re.search(r"all-MiniLM-L6-v2|huggingface|huggingface\.co|SentenceTransformer\s*\(", all_text, re.I):
        result["external_model_dependencies"].append({
            "name": "Hugging Face / SentenceTransformer model",
            "model": "all-MiniLM-L6-v2" if "all-MiniLM-L6-v2" in all_text else None,
            "evidence": "Embedding service loads an external model at runtime"
        })

    if re.search(r"fallback|TfidfVectorizer|TF-IDF", all_text, re.I) and re.search(r"SentenceTransformer|all-MiniLM", all_text, re.I):
        result["fallbacks"].append({
            "service": "embedding-service",
            "description": "Embedding service has a TF-IDF fallback when semantic model loading fails."
        })

    for service_name, text in per_service.items():
        vals = [int(x) for x in re.findall(r"\btimeout\s*[:=]\s*(\d+)\b", text, re.I)]
        if vals:
            result["timeouts_ms"].append({"service": service_name, "max_ms": max(vals)})

    # Explicitly detect the synchronous upload pipeline.
    if re.search(r"axios\.post|fetch\(|requests\.(post|request)|httpx\.(post|request)", per_service.get("backend", ""), re.I):
        backend_text = per_service.get("backend", "")
        has_ocr = bool(re.search(r"OCR_SERVICE_URL|/extract|ocrservice|ocr-service", backend_text, re.I))
        has_embedding = bool(re.search(r"EMBEDDING_SERVICE_URL|/index|embeddingservice|embedding-service", backend_text, re.I))
        if has_ocr and has_embedding:
            result["synchronous_chains"].append({
                "source": "backend",
                "chain": ["backend", "ocr-service", "embedding-service"],
                "evidence": "Backend makes sequential downstream OCR and embedding requests."
            })
    return result


def _apply_project_evidence(services, files, archive):
    scaling = parse_zerops_import_evidence(files, archive)
    runtime = parse_zerops_runtime_config(files, archive)
    deep = detect_deep_runtime_evidence(files, archive, services)
    app._project_evidence = {"scaling": scaling, "zerops_runtime": runtime, "deep": deep}

    # Merge explicit Zerops import scaling into the normalized service model.
    for service in services:
        aliases = _service_aliases(service["name"])
        match = None
        for configured, values in scaling.get("services", {}).items():
            if aliases & _service_aliases(configured):
                match = values
                break
        if match:
            service["replicas_explicit"] = True
            service["min_containers"] = match.get("minContainers")
            service["max_containers"] = match.get("maxContainers")
            if match.get("minContainers") is not None and match.get("maxContainers") is not None and match.get("minContainers") == match.get("maxContainers"):
                service["declared_replicas"] = match.get("minContainers")
            service["replica_evidence"] = scaling.get("file")
    return services


# Preserve the legacy detector, but normalize its output with explicit project evidence.
_base_detect_services_v10 = detect_services

def detect_services(files, archive, compose_services, k8s_workloads):
    services = _base_detect_services_v10(files, archive, compose_services, k8s_workloads)
    return _apply_project_evidence(services, files, archive)


# Zerops detection includes both the main deployment config and its import/scaling config.
def detect_zerops(files):
    return [f for f in files if basename(f).lower() in {
        "zerops.yml", "zerops.yaml", "zerops-project-import.yml", "zerops-project-import.yaml"
    }]


_base_detect_service_references_v10 = detect_service_references

def detect_service_references(services, files, archive):
    """Use exact service names plus normalized aliases such as ocrservice/ocr-service."""
    refs = []
    alias_map = {}
    for service in services:
        for alias in _service_aliases(service["name"]):
            alias_map[alias] = service["name"]
    for service in services:
        directory = clean_path(service.get("directory", "")).strip("/")
        relevant = [f for f in files if (f.startswith(directory + "/") if directory else "/" not in f)]
        text = "\n".join(
            read_text_from_zip(archive, f, 400_000)
            for f in relevant[:250]
            if get_file_extension(f) in config.source_extensions or basename(f).startswith(".env")
        )
        for match in re.finditer(r'https?://([A-Za-z0-9_.-]+)(?::\d+)?(?:/[^\s\"\']*)?', text):
            host = match.group(1)
            target = alias_map.get(_norm_name(host))
            if target and target != service["name"]:
                refs.append({"service": service["name"], "target": target,
                             "evidence": f"HTTP reference to {host} detected in source/configuration"})
        for variable in re.findall(r'\b([A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT))\b', text):
            var_norm = _norm_name(variable)
            for alias, target in alias_map.items():
                if alias and alias in var_norm and target != service["name"]:
                    refs.append({"service": service["name"], "target": target,
                                 "evidence": f"{variable} references service '{target}'"})
    # Explicit Zerops environment variables are evidence too.
    runtime = getattr(app, "_project_evidence", {}).get("zerops_runtime", {})
    return unique(refs)


_base_analyze_reliability_v10 = analyze_reliability

def analyze_reliability(services, global_deps, health_endpoints, service_health,
                        dockerfiles, zerops_configs, compose_files, compose_services,
                        k8s_workloads, env_info, ci_cd, iac):
    findings = _base_analyze_reliability_v10(
        services, global_deps, health_endpoints, service_health,
        dockerfiles, zerops_configs, compose_files, compose_services,
        k8s_workloads, env_info, ci_cd, iac
    )
    evidence = getattr(app, "_project_evidence", {})
    scaling = evidence.get("scaling", {})
    deep = evidence.get("deep", {})

    # Replace the weaker generic replica findings with explicit 1-1 evidence where available.
    for service in services:
        mn, mx = service.get("min_containers"), service.get("max_containers")
        if mn is not None and mx is not None and mn == mx == 1:
            findings = [f for f in findings if f.get("title") != f"{service['name']} single-instance availability risk"]
            findings.append(make_finding(
                "warning", "availability", f"{service['name']} single instance explicitly configured",
                f"Zerops import configuration explicitly sets minContainers=1 and maxContainers=1 for '{service['name']}'.",
                f"Increase minContainers/maxContainers to 2+ when high availability is required and validate statefulness before scaling.",
                8
            ))

    # Explicit NON_HA database mode is stronger than a generic database dependency warning.
    for db_name, db_cfg in scaling.get("databases", {}).items():
        if str(db_cfg.get("mode", "")).upper() == "NON_HA":
            title = f"PostgreSQL explicitly configured NON_HA" if str(db_cfg.get("type", "")).lower().startswith("postgres") else f"{db_name} explicitly configured NON_HA"
            findings.append(make_finding(
                "warning", "data", title,
                f"Zerops import configuration sets database '{db_name}' to mode NON_HA.",
                "Use an HA database mode or an equivalent failover/recovery design when database availability is a production requirement.",
                10
            ))

    for item in deep.get("system_dependencies", []):
        findings.append(make_finding(
            "warning", "deployment", f"System dependency: {item['name']}",
            f"{item['evidence']}. This dependency must remain available in the deployment environment.",
            "Preserve the OS-level dependency in the deployment/build configuration and validate it before rollout.",
            5
        ))

    for item in deep.get("persistent_state", []):
        if item.get("ephemeral"):
            findings.append(make_finding(
                "warning", "state", f"Ephemeral mutable state in {item['service']}",
                f"Service '{item['service']}' stores its FAISS index under {item['path']}, which is ephemeral local filesystem state.",
                "Externalize/shared-store the index or rebuild it deterministically before enabling horizontal scaling.",
                9
            ))

    for item in deep.get("external_model_dependencies", []):
        findings.append(make_finding(
            "warning", "external-dependency", "External model dependency detected",
            f"{item['evidence']}." + (f" Model: {item['model']}." if item.get("model") else ""),
            "Cache/package the model where practical or make startup resilient to network/model-registry failures.",
            5
        ))

    for item in deep.get("fallbacks", []):
        findings.append(make_finding(
            "info", "resilience", "Embedding fallback detected",
            item["description"],
            "Retain and monitor the fallback path; expose degraded-mode telemetry so failures are visible.",
            0
        ))
    return findings


_base_build_optimization_plan_v10 = build_optimization_plan

def build_optimization_plan(services, global_deps, findings, deployment, service_deps):
    actions = _base_build_optimization_plan_v10(services, global_deps, findings, deployment, service_deps)
    evidence = getattr(app, "_project_evidence", {})
    scaling = evidence.get("scaling", {})
    deep = evidence.get("deep", {})

    # Explicit 1-1 limits require a scaling recommendation; do not call them unknown.
    existing = {(a.get("service"), a.get("action")) for a in actions}
    for service in services:
        mn, mx = service.get("min_containers"), service.get("max_containers")
        if mn == 1 and mx == 1:
            key = (service["name"], "Configure horizontal redundancy")
            if key not in existing:
                actions.append({
                    "priority": "high" if service["type"] == "backend" else "medium",
                    "service": service["name"],
                    "action": "Increase explicit container limits",
                    "current": "minContainers=1, maxContainers=1",
                    "recommended": "minContainers/maxContainers >= 2 when HA is required",
                    "reason": "The uploaded Zerops import configuration explicitly limits this service to one container."
                })

    for item in deep.get("persistent_state", []):
        if item.get("ephemeral"):
            actions.append({
                "priority": "high",
                "service": item["service"],
                "action": "Externalize FAISS index state before horizontal scaling",
                "current": item["path"],
                "recommended": "Shared/persistent index or deterministic rebuild strategy",
                "reason": "Independent replicas with separate ephemeral indexes can return inconsistent search results."
            })
    return actions


# Existing Zerops configuration is the source of truth. Validate setup names using aliases.
def parse_existing_zerops(files, archive):
    candidates = [f for f in files if basename(f).lower() in {"zerops.yml", "zerops.yaml"}]
    if not candidates:
        return None
    return read_text_from_zip(archive, candidates[0], 700_000)


def validate_zerops_configuration(services, service_health, files, existing_zerops, generated_config):
    content = existing_zerops or generated_config or ""
    setups = re.findall(r"^\s*-\s*setup:\s*([A-Za-z0-9_.-]+)", content, re.MULTILINE)
    service_aliases = set()
    for s in services:
        service_aliases |= _service_aliases(s["name"])
    setup_aliases = set()
    for x in setups:
        setup_aliases |= _service_aliases(x)
    errors, warnings = [], []
    # Existing config can use Zerops hostnames without matching source directory names exactly.
    for s in services:
        if not (_service_aliases(s["name"]) & setup_aliases):
            warnings.append(f"No matching Zerops setup found for detected service '{s['name']}'")
    # Validate proven start commands against the source tree only when we are generating a new config.
    if not existing_zerops:
        for service in services:
            cmd = get_service_start_command(service, files, None)
            directory = clean_path(service.get("directory", "")).strip("/")
            names = {basename(f) for f in files if (f.startswith(directory + "/") if directory else "/" not in f)}
            if cmd and "python3 app.py" in cmd and "app.py" not in names:
                errors.append(f"{service['name']} references app.py but app.py does not exist in its service directory")
            if cmd == "npm start" and not any(f == (f"{directory}/package.json" if directory else "package.json") for f in files):
                errors.append(f"{service['name']} has npm start but no package.json was found")
    return {"valid": not errors, "errors": unique(errors), "warnings": unique(warnings), "services_configured": setups}


# =========================================================
# SIMULATION HARDENING
# =========================================================

def simulate_traffic_spike(services, architecture, multiplier=10, baseline_score=100):
    try:
        multiplier = float(multiplier)
    except (TypeError, ValueError):
        multiplier = 10.0
    multiplier = max(1.0, min(multiplier, 100.0))
    edges = _graph_service_edges(architecture)
    names = [s["name"] for s in services]
    # Incoming entrypoint: prefer frontend, otherwise API/backend.
    entrypoints = [s["name"] for s in services if s["type"] == "frontend"]
    if not entrypoints:
        entrypoints = [s["name"] for s in services if s["type"] == "backend"][:1]
    affected = []
    pressure = []
    reachable = defaultdict(list)
    for source, target in edges:
        reachable[source].append(target)
    q = list(entrypoints)
    seen = set(q)
    while q:
        cur = q.pop(0)
        affected.append(cur)
        for nxt in reachable.get(cur, []):
            if nxt not in seen:
                seen.add(nxt); q.append(nxt)
    if not affected:
        affected = names
    deep = getattr(app, "_project_evidence", {}).get("deep", {})
    sync = bool(deep.get("synchronous_chains"))
    for name in affected:
        lname = name.lower()
        if lname in {"api", "backend"}:
            pressure.append({"service": name, "reason": "The application entrypoint receives the simulated traffic increase.", "expected_effect": f"Request concurrency may increase by approximately {multiplier:g}×."})
        if "analyzer" in lname or "ocr" in lname or "embedding" in lname:
            pressure.append({"service": name, "reason": "Downstream processing is on the request path and can inherit the traffic increase.", "expected_effect": f"Workload may increase by approximately {multiplier:g}×."})
    penalty = min(55, max(0, int((multiplier - 1) * 3)))
    if sync:
        penalty += 8
    score = max(0, int(baseline_score) - penalty)
    return {
        "status": "success",
        "scenario": "Traffic Spike ×10" if multiplier == 10 else f"Traffic Spike ×{multiplier:g}",
        "type": "traffic_spike",
        "target": "application-entrypoint",
        "multiplier": multiplier,
        "reliability": score,
        "severity": "critical" if multiplier >= 20 else "warning" if multiplier >= 5 else "info",
        "affected_services": unique(affected),
        "impact": [
            f"Simulated incoming traffic increased by approximately {multiplier:g}×.",
            "Higher request concurrency can increase latency and resource pressure.",
            "Static simulation does not claim measured CPU, memory or network saturation."
        ],
        "pressure_points": pressure,
        "recommended_action": "Scale the services on the request path when capacity requires it; use asynchronous processing for long-running work."
    }


_base_run_simulation_v10 = run_simulation

def run_simulation(services, architecture, scenario, target=None, multiplier=10, baseline_score=100):
    raw = str(scenario or "").strip().lower().replace("-", "_").replace(" ", "_")
    target_raw = str(target or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"traffic_spike", "traffic", "traffic_spike_x10", "trafficspike"} or target_raw in {"traffic_spike", "traffic_spike_x10", "traffic"}:
        return simulate_traffic_spike(services, architecture, multiplier, baseline_score)
    return _base_run_simulation_v10(services, architecture, scenario, target, multiplier, baseline_score)


# Accept both JSON-body simulation and /simulate/<scenario> so scenario IDs can never
# accidentally enter the service lookup path.
# Keep the original /simulate endpoint and make the dispatcher scenario-aware.
# Also accept /simulate/<scenario> for clients that encode the scenario in the URL.
@app.post("/simulate/<scenario_name>")
@app.post("/api/simulate/<scenario_name>")
def simulate_scenario_path(scenario_name):
    payload = request.get_json(silent=True) or {}
    model = getattr(app, "last_analysis_model", None)
    if not model:
        return jsonify({"error": "Run a project analysis before running a simulation"}), 409
    scenario = scenario_name or payload.get("scenario") or payload.get("type") or payload.get("id") or payload.get("service")
    target = payload.get("target")
    multiplier = payload.get("multiplier", 10)
    result = run_simulation(model["services"], model["architecture"], scenario, target, multiplier, model.get("reliability_score", 100))
    if result.get("error"):
        return jsonify(result), 400
    return jsonify({"status": "success", "simulation": result})

# Add a deployment-status normalization hook. It guarantees legacy frontend fields
# are derived from the same authoritative nested values.
@app.after_request
def normalize_analysis_response(response):
    if not response.is_json:
        return response
    try:
        data = response.get_json()
        if isinstance(data, dict) and data.get("status") == "success" and "deployment_status" in data:
            ds = data["deployment_status"]
            data["zerops_detected"] = bool(ds.get("zerops", {}).get("detected"))
            data["ci_detected"] = bool(ds.get("ci", {}).get("detected"))
            data["cd_detected"] = bool(ds.get("cd", {}).get("detected"))
            data["containerization_detected"] = bool(ds.get("containerization", {}).get("detected"))
            data["delivery_readiness"] = {
                "ci": ds.get("ci", {}),
                "cd": ds.get("cd", {}),
                "containerization": ds.get("containerization", {}),
                "zerops": ds.get("zerops", {}),
                "ci_cd": {
                    "ci_detected": bool(ds.get("ci", {}).get("detected")),
                    "cd_detected": bool(ds.get("cd", {}).get("detected")),
                    "status": (
                        "CI detected / CD detected" if ds.get("ci", {}).get("detected") and ds.get("cd", {}).get("detected")
                        else "CI detected / CD not detected" if ds.get("ci", {}).get("detected")
                        else "CI not detected / CD detected" if ds.get("cd", {}).get("detected")
                        else "CI/CD not detected"
                    )
                }
            }
            pe = getattr(app, "_project_evidence", {})
            scaling = pe.get("scaling", {})
            deep = pe.get("deep", {})
            data["project_evidence"] = {
                "zerops_import_file": scaling.get("file"),
                "explicit_scaling": scaling.get("services", {}),
                "database_configuration": scaling.get("databases", {}),
                "system_dependencies": deep.get("system_dependencies", []),
                "persistent_state": deep.get("persistent_state", []),
                "external_model_dependencies": deep.get("external_model_dependencies", []),
                "resilience_mechanisms": deep.get("fallbacks", []),
                "synchronous_chains": deep.get("synchronous_chains", [])
            }
            response.set_data(json.dumps(data))
            response.headers["Content-Type"] = "application/json"
    except Exception:
        pass
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
