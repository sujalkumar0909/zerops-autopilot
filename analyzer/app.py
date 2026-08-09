from flask import Flask, request, jsonify
import json
import os
import re
import tempfile
import zipfile
from urllib.parse import urlparse

app = Flask(__name__)


VERSION = "6.0"

MAX_TEXT_FILE = 1_500_000
MAX_CODE_FILE = 500_000
MAX_TOTAL_PROJECT_TEXT = 15_000_000

IGNORED_DIRECTORIES = {
    "node_modules", ".git", ".next", "dist", "build", "coverage",
    "__pycache__", ".venv", "venv", ".pytest_cache", ".idea",
    ".vscode", ".turbo", ".cache", ".parcel-cache", "target",
    "vendor", ".mypy_cache", ".ruff_cache", ".tox", ".terraform",
    ".gradle", ".pytest_cache"
}

SOURCE_EXTENSIONS = {
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".java",
    ".go", ".rs", ".rb", ".php", ".cs", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".properties", ".xml", ".env"
}

CODE_EXTENSIONS = {
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".java",
    ".go", ".rs", ".rb", ".php", ".cs"
}

MANIFESTS = {
    "package.json": "Node.js",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "pipfile": "Python",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Java",
    "go.mod": "Go",
    "cargo.toml": "Rust",
    "gemfile": "Ruby",
    "composer.json": "PHP",
}

HEALTH_ROUTE_PATTERN = re.compile(
    r"""["'`]((?:/[\w.-]+)*/(?:health|healthz|ready|readiness|live|liveness)(?:/[\w.-]*)?)["'`]""",
    re.I,
)

URL_PATTERN = re.compile(
    r"""https?://[A-Za-z0-9._:-]+(?::\d+)?(?:/[^\s"'`<>)]*)?""",
    re.I,
)

PORT_PATTERNS = [
    re.compile(r"\bPORT\s*=\s*[\"']?(\d{2,5})", re.I),
    re.compile(r"\bport\s*[:=]\s*[\"']?(\d{2,5})", re.I),
    re.compile(r"\blisten\s*\(\s*[\"']?(\d{2,5})", re.I),
    re.compile(r"\bEXPOSE\s+(\d{2,5})", re.I),
    re.compile(r"\b--port[=\s]+(\d{2,5})", re.I),
]

FRAMEWORK_RULES = {
    "Next.js": {"next"},
    "React": {"react", "react-dom"},
    "Vite": {"vite"},
    "Express": {"express"},
    "FastAPI": {"fastapi"},
    "Flask": {"flask"},
    "Django": {"django"},
    "Spring Boot": {"spring-boot"},
    "NestJS": {"@nestjs/core"},
    "Vue": {"vue"},
    "Angular": {"@angular/core"},
    "Svelte": {"svelte"},
}

DATABASE_PATTERNS = {
    "PostgreSQL": {"postgres", "postgresql", "psycopg", "asyncpg", "pg"},
    "MySQL": {"mysql", "mysql2", "pymysql"},
    "MongoDB": {"mongodb", "mongoose", "pymongo"},
    "Redis": {"redis", "ioredis", "redis-py"},
    "SQLite": {"sqlite", "sqlite3"},
    "MariaDB": {"mariadb"},
    "Cassandra": {"cassandra"},
    "DynamoDB": {"dynamodb"},
}

QUEUE_PATTERNS = {
    "RabbitMQ": {"rabbitmq", "amqp", "pika"},
    "Kafka": {"kafka", "confluent-kafka"},
    "BullMQ": {"bullmq"},
    "Bull": {"bull"},
    "Celery": {"celery"},
    "AWS SQS": {"sqs"},
    "Google Pub/Sub": {"pubsub"},
}

CACHE_PATTERNS = {
    "Redis": {"redis", "ioredis", "redis-py"},
    "Memcached": {"memcached"},
}

STORAGE_PATTERNS = {
    "S3 / Object Storage": {"s3", "aws-sdk", "boto3", "minio", "objectstorage"},
}

SECRET_NAME_PATTERN = re.compile(
    r"(PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|ACCESS_KEY|"
    r"CLIENT_SECRET|DATABASE_URL|DB_URL|JWT_SECRET|AWS_SECRET)",
    re.I,
)

ENV_URL_NAME_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT)[A-Z0-9_]*\b"
)

DOCKERFILE_NAME_PATTERN = re.compile(
    r"^(?:[\w.-]*\.)?(?:dockerfile|containerfile)(?:\.[\w.-]+)?$",
    re.I,
)

CI_BASENAMES = {
    "jenkinsfile",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    ".travis.yml",
    "circleci",
}

# ------------------------------------------------------------
# Generic helpers
# ------------------------------------------------------------

def clean_path(path):
    path = str(path).replace("\\", "/")
    path = re.sub(r"^\./+", "", path)
    return path.strip("/")


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


def is_ignored(path):
    parts = clean_path(path).split("/")
    return any(part.lower() in IGNORED_DIRECTORIES for part in parts)


def is_dockerfile_name(name):
    return bool(DOCKERFILE_NAME_PATTERN.match(name))


def extension(path):
    return os.path.splitext(clean_path(path))[1].lower()


def read_text_from_zip(archive, filename, max_bytes=MAX_TEXT_FILE):
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


def get_directories(files):
    directories = {}
    for file in files:
        if is_ignored(file):
            continue
        parts = clean_path(file).split("/")
        for index in range(1, len(parts)):
            directory = "/".join(parts[:index])
            directories.setdefault(directory, []).append(file)
    return directories


def path_inside(path, directory):
    path = clean_path(path)
    directory = clean_path(directory).strip("/")
    if not directory:
        return "/" not in path
    return path == directory or path.startswith(directory + "/")


def relative_file_in_service(file, directory):
    if not directory or directory == ".":
        return file
    prefix = clean_path(directory).rstrip("/") + "/"
    return file[len(prefix):] if file.startswith(prefix) else file


def service_files(files, directory):
    if not directory or directory == ".":
        return [f for f in files if "/" not in f]
    return [f for f in files if path_inside(f, directory)]


# ------------------------------------------------------------
# Project manifests and technology detection
# ------------------------------------------------------------

def detect_manifest_type(directory_files):
    names = {basename(f) for f in directory_files}
    for manifest, technology in MANIFESTS.items():
        if manifest in names:
            return technology
    if any(name.endswith(".csproj") for name in names):
        return "C#"
    return "Unknown"


def read_package_json(archive, file):
    return safe_json(read_text_from_zip(archive, file))


def detect_frameworks(directory_files, archive):
    found = []

    for file in directory_files:
        if basename(file) != "package.json":
            continue
        package = read_package_json(archive, file)
        deps = {}
        deps.update(package.get("dependencies", {}) or {})
        deps.update(package.get("devDependencies", {}) or {})
        names = {str(k).lower() for k in deps}
        for framework, rules in FRAMEWORK_RULES.items():
            if any(rule.lower() in names for rule in rules):
                found.append(framework)

    text_parts = []
    for file in directory_files:
        if extension(file) in CODE_EXTENSIONS:
            text_parts.append(read_text_from_zip(archive, file, 200_000).lower())
    text = "\n".join(text_parts)

    source_rules = {
        "FastAPI": ("from fastapi", "import fastapi"),
        "Flask": ("from flask", "import flask"),
        "Django": ("import django", "from django"),
        "Spring Boot": ("springboot", "spring boot"),
    }

    for framework, rules in source_rules.items():
        if any(rule in text for rule in rules):
            found.append(framework)

    return unique(found)


def detect_service_technology(directory_files, archive):
    manifest = detect_manifest_type(directory_files)

    if manifest in {"Node.js", "Python"}:
        frameworks = detect_frameworks(directory_files, archive)
        return f"{manifest} / {' + '.join(frameworks)}" if frameworks else manifest

    return manifest


def detect_technologies(files, archive):
    technologies = []

    if any(basename(f) == "package.json" for f in files):
        technologies.append("Node.js / JavaScript")
    if any(basename(f) in {"requirements.txt", "pyproject.toml", "pipfile"} for f in files):
        technologies.append("Python")
    if any(basename(f) in {"pom.xml", "build.gradle", "build.gradle.kts"} for f in files):
        technologies.append("Java")
    if any(basename(f) == "go.mod" for f in files):
        technologies.append("Go")
    if any(basename(f) == "cargo.toml" for f in files):
        technologies.append("Rust")
    if any(is_dockerfile_name(basename(f)) for f in files):
        technologies.append("Docker / OCI")
    if detect_compose_files(files):
        technologies.append("Docker Compose")
    if detect_kubernetes_files(files, archive):
        technologies.append("Kubernetes manifests")

    return unique(technologies)


# ------------------------------------------------------------
# Compose detection
#
# This intentionally remains a lightweight parser so the analyzer
# has no external YAML dependency. It handles the common Compose
# structures needed for architecture inference.
# ------------------------------------------------------------

def detect_compose_files(files):
    names = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
    return [f for f in files if basename(f) in names]


def parse_compose_services(archive, compose_files):
    services = {}

    for compose_file in compose_files:
        text = read_text_from_zip(archive, compose_file)
        in_services = False
        current = None
        block = None

        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue

            indent = len(raw) - len(raw.lstrip(" "))
            stripped = raw.strip()

            if indent == 0 and stripped == "services:":
                in_services = True
                current = None
                block = None
                continue

            if not in_services:
                continue

            # A new service is normally two spaces under services.
            if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
                name = stripped[:-1].strip().strip("'\"")
                if name:
                    current = name
                    services.setdefault(name, {
                        "name": name,
                        "file": compose_file,
                        "image": None,
                        "build": None,
                        "build_context": None,
                        "dockerfile": None,
                        "ports": [],
                        "depends_on": [],
                        "replicas": 1,
                        "environment": {},
                    })
                block = None
                continue

            if not current:
                continue

            entry = services[current]

            if indent == 4:
                if stripped.startswith("image:"):
                    entry["image"] = stripped.split(":", 1)[1].strip().strip("'\"")
                    block = None

                elif stripped.startswith("build:"):
                    value = stripped.split(":", 1)[1].strip().strip("'\"")
                    if value:
                        entry["build"] = value
                        entry["build_context"] = value
                        block = None
                    else:
                        block = "build"

                elif stripped == "ports:":
                    block = "ports"

                elif stripped == "depends_on:":
                    block = "depends_on"

                elif stripped == "environment:":
                    block = "environment"

                else:
                    match = re.match(r"replicas\s*:\s*(\d+)", stripped)
                    if match:
                        entry["replicas"] = int(match.group(1))
                    block = None
                continue

            if indent >= 6 and block == "build":
                if stripped.startswith("context:"):
                    entry["build_context"] = stripped.split(":", 1)[1].strip().strip("'\"")
                elif stripped.startswith("dockerfile:"):
                    entry["dockerfile"] = stripped.split(":", 1)[1].strip().strip("'\"")
                continue

            if indent >= 6 and block == "ports":
                # Supports "3000:3000", "127.0.0.1:3000:3000",
                # "3000", and quoted versions.
                value = stripped.lstrip("- ").strip().strip("'\"")
                numbers = re.findall(r"\d+", value)
                if numbers:
                    try:
                        port = int(numbers[-1])
                        if 1 <= port <= 65535:
                            entry["ports"].append(port)
                    except ValueError:
                        pass
                continue

            if indent >= 6 and block == "depends_on":
                value = stripped.lstrip("- ").strip().strip("'\"")
                # Compose can also use:
                #   depends_on:
                #     api:
                #       condition: service_healthy
                if value and re.match(r"^[A-Za-z0-9_.-]+$", value) and ":" not in value:
                    entry["depends_on"].append(value)
                continue

            if indent >= 6 and block == "environment":
                value = stripped.lstrip("- ").strip()
                if "=" in value:
                    key, val = value.split("=", 1)
                    entry["environment"][key.strip()] = val.strip().strip("'\"")
                elif ":" in value:
                    key, val = value.split(":", 1)
                    entry["environment"][key.strip()] = val.strip().strip("'\"")
                continue

    for item in services.values():
        item["ports"] = unique(item["ports"])
        item["depends_on"] = unique(item["depends_on"])

    return list(services.values())


# ------------------------------------------------------------
# Kubernetes detection
# ------------------------------------------------------------

def detect_kubernetes_files(files, archive):
    result = []
    for file in files:
        if extension(file) not in {".yml", ".yaml"}:
            continue
        text = read_text_from_zip(archive, file, 800_000)
        if re.search(
            r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service)\s*$",
            text,
        ):
            result.append(file)
    return result


def parse_kubernetes_workloads(files, archive):
    workloads = []

    for file in files:
        text = read_text_from_zip(archive, file, 1_000_000)

        kind = re.search(r"(?m)^\s*kind\s*:\s*([A-Za-z0-9]+)\s*$", text)
        name = re.search(
            r"(?ms)metadata:\s*\n(?:\s+[^\n]+\n)*?\s+name\s*:\s*([A-Za-z0-9_.-]+)",
            text,
        )
        replicas = re.search(r"(?m)^\s*replicas\s*:\s*(\d+)\s*$", text)

        if not kind or not name:
            continue

        if kind.group(1) not in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
            continue

        workloads.append({
            "name": name.group(1),
            "kind": kind.group(1),
            "replicas": int(replicas.group(1)) if replicas else 1,
            "file": file,
        })

    return workloads


# ------------------------------------------------------------
# Service identification
# ------------------------------------------------------------

def service_role_from_evidence(name, technology, frameworks, directory_files, archive):
    """
    Role is inferred from application evidence rather than a fixed
    list of project-specific directory names.
    """

    framework_set = {f.lower() for f in frameworks}

    if framework_set.intersection({"react", "next.js", "vite", "vue", "angular", "svelte"}):
        return "frontend"

    # Read only a bounded amount of source code for behavioral clues.
    text = []
    for file in directory_files:
        if extension(file) in CODE_EXTENSIONS:
            text.append(read_text_from_zip(archive, file, 150_000).lower())
    source = "\n".join(text)

    worker_signals = (
        "celery", "bullmq", "bull(", "rq.worker", "dramatiq",
        "kafkaconsumer", "consumer(", "rabbitmq", "background_tasks",
    )
    if any(signal in source for signal in worker_signals):
        return "worker"

    # Server-side frameworks and server entrypoints are backend-like.
    server_frameworks = {
        "express", "fastapi", "flask", "django", "spring boot", "nestjs"
    }
    if framework_set.intersection(server_frameworks):
        return "backend"

    if technology != "Unknown":
        # A service manifest without frontend evidence is safest to
        # classify as backend/application rather than inventing a role.
        return "backend"

    return "unknown"


def root_manifest_files(files):
    return [f for f in files if "/" not in f]


def directory_manifest_services(files, archive):
    services = []

    for directory, directory_files in get_directories(files).items():
        technology = detect_service_technology(directory_files, archive)
        if technology == "Unknown":
            continue

        frameworks = detect_frameworks(directory_files, archive)
        role = service_role_from_evidence(
            os.path.basename(directory), technology, frameworks, directory_files, archive
        )

        services.append({
            "name": os.path.basename(directory),
            "technology": technology,
            "type": role,
            "directory": directory,
            "frameworks": frameworks,
            "source": "manifest",
            "replicas": 1,
        })

    return services


def root_application_service(files, archive):
    root_files = root_manifest_files(files)
    technology = detect_service_technology(root_files, archive)

    if technology == "Unknown":
        return None

    frameworks = detect_frameworks(root_files, archive)
    role = service_role_from_evidence(
        "application", technology, frameworks, root_files, archive
    )

    return {
        "name": "application",
        "technology": technology,
        "type": role,
        "directory": ".",
        "frameworks": frameworks,
        "source": "root-manifest",
        "replicas": 1,
    }


def compose_service_hints(item):
    hints = []

    context = clean_path(item.get("build_context") or "").strip("/")
    if context and context != ".":
        hints.append(os.path.basename(context).lower())

    dockerfile = clean_path(item.get("dockerfile") or "")
    if dockerfile:
        stem = os.path.splitext(os.path.basename(dockerfile))[0].lower()
        if stem:
            hints.append(stem)
        parent = os.path.dirname(dockerfile)
        if parent:
            hints.append(os.path.basename(parent).lower())

    return unique(hints)


def infer_container_technology(item, archive, compose_file=None):
    image = (item.get("image") or "").lower()
    if "node" in image:
        return "Node.js / Container"
    if "python" in image:
        return "Python / Container"
    if "nginx" in image:
        return "Nginx / Container"
    if image:
        return f"Container ({item['image']})"

    dockerfile = item.get("dockerfile")
    if dockerfile and compose_file:
        base = detect_dockerfile_base(archive, resolve_compose_path(compose_file, dockerfile))
        if base:
            return f"{base} / Container"

    return "Container"


def resolve_compose_path(compose_file, dockerfile):
    dockerfile = clean_path(dockerfile)
    if dockerfile.startswith("/"):
        return dockerfile.strip("/")
    base = os.path.dirname(clean_path(compose_file))
    return clean_path(os.path.join(base, dockerfile))


def detect_dockerfile_base(archive, path):
    text = read_text_from_zip(archive, path, 300_000)
    match = re.search(r"(?im)^\s*FROM\s+([^\s]+)", text)
    if not match:
        return None

    image = match.group(1).lower()
    if "node" in image:
        return "Node.js"
    if "python" in image:
        return "Python"
    if "openjdk" in image or "temurin" in image or "eclipse-temurin" in image:
        return "Java"
    if "golang" in image:
        return "Go"
    if "rust" in image:
        return "Rust"
    return "Container"


def merge_service(existing, incoming):
    existing["frameworks"] = unique(
        existing.get("frameworks", []) + incoming.get("frameworks", [])
    )
    existing["ports"] = unique(
        existing.get("ports", []) + incoming.get("ports", [])
    )
    existing["depends_on"] = unique(
        existing.get("depends_on", []) + incoming.get("depends_on", [])
    )

    if incoming.get("declared_replicas", 1) > existing.get("declared_replicas", 1):
        existing["declared_replicas"] = incoming["declared_replicas"]

    for key in ("image", "build", "build_context", "dockerfile", "compose_names"):
        if incoming.get(key):
            if isinstance(incoming[key], list):
                existing[key] = unique(existing.get(key, []) + incoming[key])
            elif not existing.get(key):
                existing[key] = incoming[key]

    return existing


def detect_services(files, archive, compose_services, k8s_workloads):
    services = directory_manifest_services(files, archive)

    root = root_application_service(files, archive)
    if root and not any(s.get("directory") == "." for s in services):
        services.append(root)

    aliases = {}

    # Merge Compose service definitions with manifest-based services.
    for item in compose_services:
        candidates = []

        name = item["name"].lower()
        candidates.extend(
            s for s in services
            if s["name"].lower() == name
        )

        for hint in compose_service_hints(item):
            candidates.extend(
                s for s in services
                if s.get("directory")
                and os.path.basename(clean_path(s["directory"])).lower() == hint
            )

        matched = candidates[0] if candidates else None

        if matched:
            incoming = {
                "ports": item.get("ports", []),
                "depends_on": item.get("depends_on", []),
                "declared_replicas": item.get("replicas", 1),
                "image": item.get("image"),
                "build": item.get("build"),
                "build_context": item.get("build_context"),
                "dockerfile": item.get("dockerfile"),
                "compose_names": [item["name"]],
            }
            merge_service(matched, incoming)
            aliases[item["name"]] = matched["name"]
        else:
            role = "backend"
            # Do not classify a service as frontend merely because its
            # name happens to be "frontend". Infer from its build context
            # or image where possible.
            context = item.get("build_context") or item.get("build") or ""
            context_files = [
                f for f in files
                if path_inside(f, context)
            ] if context else []

            technology = (
                detect_service_technology(context_files, archive)
                if context_files else "Unknown"
            )

            frameworks = detect_frameworks(context_files, archive) if context_files else []
            if technology == "Unknown":
                technology = infer_container_technology(item, archive, item.get("file"))

            role = service_role_from_evidence(
                item["name"], technology, frameworks, context_files, archive
            )
            if role == "unknown":
                role = "backend"

            service = {
                "name": item["name"],
                "technology": technology,
                "type": role,
                "directory": context,
                "frameworks": frameworks,
                "source": "compose",
                "ports": unique(item.get("ports", [])),
                "depends_on": unique(item.get("depends_on", [])),
                "declared_replicas": item.get("replicas", 1),
                "image": item.get("image"),
                "build": item.get("build"),
                "build_context": item.get("build_context"),
                "dockerfile": item.get("dockerfile"),
                "compose_names": [item["name"]],
            }
            services.append(service)
            aliases[item["name"]] = item["name"]

    # Add Kubernetes workloads that aren't already represented.
    existing_names = {s["name"].lower() for s in services}
    for workload in k8s_workloads:
        if workload["name"].lower() in existing_names:
            continue

        services.append({
            "name": workload["name"],
            "technology": "Kubernetes",
            "type": "backend",
            "directory": "",
            "frameworks": [],
            "source": "kubernetes",
            "declared_replicas": workload["replicas"],
            "kubernetes_kind": workload["kind"],
        })

    # Initialize fields consistently.
    for service in services:
        service.setdefault("ports", [])
        service.setdefault("depends_on", [])
        service.setdefault("replicas", 1)
        service["ports"] = unique(service["ports"])
        service["depends_on"] = unique(service["depends_on"])

    # De-duplicate physical services.
    result = []
    seen = set()
    for service in services:
        key = (
            service["name"].lower(),
            clean_path(service.get("directory", "")),
            service["type"],
        )
        if key not in seen:
            seen.add(key)
            result.append(service)

    return result, aliases


def resolve_alias(name, aliases):
    seen = set()
    current = name
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


# ------------------------------------------------------------
# Service commands / deployment evidence
# ------------------------------------------------------------

def find_manifest_for_service(service, files):
    directory = clean_path(service.get("directory", ""))
    candidates = service_files(files, directory)
    names = {basename(f): f for f in candidates}

    for manifest in (
        "package.json", "pyproject.toml", "requirements.txt",
        "pom.xml", "build.gradle", "build.gradle.kts",
        "go.mod", "cargo.toml", "gemfile", "composer.json"
    ):
        if manifest in names:
            return names[manifest]

    return None


def parse_package_scripts(archive, manifest_file):
    package = read_package_json(archive, manifest_file)
    return package.get("scripts", {}) or {}


def choose_node_commands(scripts):
    build = None
    start = None
    dev = None

    for key in ("build", "compile"):
        if scripts.get(key):
            build = f"npm run {key}"
            break

    for key in ("start", "serve", "prod"):
        if scripts.get(key):
            start = "npm start" if key == "start" else f"npm run {key}"
            break

    for key in ("dev", "development"):
        if scripts.get(key):
            dev = f"npm run {key}"
            break

    return build, start, dev


def parse_python_project_commands(archive, service, files):
    directory = clean_path(service.get("directory", ""))
    candidates = service_files(files, directory)

    pyproject = next((f for f in candidates if basename(f) == "pyproject.toml"), None)
    if pyproject:
        text = read_text_from_zip(archive, pyproject, 500_000)
        scripts = {}
        # PEP 621 [project.scripts] entries: name = "module:function"
        in_scripts = False
        for raw in text.splitlines():
            stripped = raw.strip()
            if stripped.startswith("[project.scripts]"):
                in_scripts = True
                continue
            if in_scripts and stripped.startswith("["):
                in_scripts = False
            if in_scripts and "=" in stripped and not stripped.startswith("#"):
                key, value = stripped.split("=", 1)
                scripts[key.strip()] = value.strip().strip("'\"")
        if scripts:
            first = next(iter(scripts))
            return f"{first}", None

    return None, None


def detect_python_entrypoint(archive, service, files):
    candidates = service_files(files, service.get("directory", ""))
    priority = [
        "app.py", "main.py", "server.py", "run.py", "wsgi.py", "manage.py"
    ]

    names = {basename(f): f for f in candidates}
    for filename in priority:
        if filename in names:
            return names[filename]

    # If no conventional name exists, inspect Python files for Flask/FastAPI
    # app objects or __main__ blocks.
    for file in candidates:
        if extension(file) != ".py":
            continue
        text = read_text_from_zip(archive, file, 250_000)
        if re.search(r"\bFlask\s*\(", text) or re.search(r"\bFastAPI\s*\(", text):
            return file

    return None


def detect_dockerfile_for_service(service, files):
    explicit = service.get("dockerfile")
    if explicit:
        candidates = [
            clean_path(explicit),
            clean_path(os.path.join(service.get("directory", ""), explicit)),
        ]
        for candidate in candidates:
            if candidate in files:
                return candidate

    directory = clean_path(service.get("directory", ""))
    for file in files:
        if not is_dockerfile_name(basename(file)):
            continue

        if directory and path_inside(file, directory):
            return file

        # A docker/ directory commonly contains service-specific Dockerfiles.
        stem = os.path.splitext(basename(file))[0].lower()
        service_name = service["name"].lower()
        if stem == service_name:
            return file

    return None


def parse_dockerfile_commands(archive, dockerfile):
    if not dockerfile:
        return {"base": None, "workdir": None, "expose": [], "cmd": None, "entrypoint": None}

    text = read_text_from_zip(archive, dockerfile, 500_000)
    base = None
    workdir = None
    expose = []
    cmd = None
    entrypoint = None

    match = re.search(r"(?im)^\s*FROM\s+([^\s]+)", text)
    if match:
        base = detect_image_language(match.group(1))

    match = re.search(r"(?im)^\s*WORKDIR\s+(.+?)\s*$", text)
    if match:
        workdir = match.group(1).strip()

    for match in re.finditer(r"(?im)^\s*EXPOSE\s+(.+?)\s*$", text):
        for number in re.findall(r"\d+", match.group(1)):
            port = int(number)
            if 1 <= port <= 65535:
                expose.append(port)

    match = re.search(r"(?im)^\s*CMD\s+(.+?)\s*$", text)
    if match:
        cmd = match.group(1).strip()

    match = re.search(r"(?im)^\s*ENTRYPOINT\s+(.+?)\s*$", text)
    if match:
        entrypoint = match.group(1).strip()

    return {
        "base": base,
        "workdir": workdir,
        "expose": unique(expose),
        "cmd": cmd,
        "entrypoint": entrypoint,
    }


def detect_image_language(image):
    value = (image or "").lower()
    if "node" in value:
        return "Node.js"
    if "python" in value:
        return "Python"
    if "java" in value or "openjdk" in value or "temurin" in value:
        return "Java"
    if "golang" in value:
        return "Go"
    if "rust" in value:
        return "Rust"
    return "Container"


def infer_service_commands(service, files, archive):
    manifest = find_manifest_for_service(service, files)
    result = {
        "manifest": manifest,
        "build_command": None,
        "start_command": None,
        "development_command": None,
        "entrypoint": None,
        "dockerfile": None,
        "docker": None,
    }

    dockerfile = detect_dockerfile_for_service(service, files)
    result["dockerfile"] = dockerfile
    if dockerfile:
        result["docker"] = parse_dockerfile_commands(archive, dockerfile)

    technology = (service.get("technology") or "").lower()

    if manifest and basename(manifest) == "package.json":
        scripts = parse_package_scripts(archive, manifest)
        build, start, dev = choose_node_commands(scripts)
        result["build_command"] = build
        result["start_command"] = start
        result["development_command"] = dev
        result["scripts"] = scripts

    elif "python" in technology:
        entry = detect_python_entrypoint(archive, service, files)
        result["entrypoint"] = entry
        if entry:
            module = os.path.splitext(os.path.basename(entry))[0]
            result["start_command"] = f"python {os.path.basename(entry)}"

    if not result["start_command"] and result["docker"]:
        docker = result["docker"]
        if docker.get("entrypoint") and docker.get("cmd"):
            result["start_command"] = f"{docker['entrypoint']} {docker['cmd']}"
        elif docker.get("entrypoint"):
            result["start_command"] = docker["entrypoint"]
        elif docker.get("cmd"):
            result["start_command"] = docker["cmd"]

    return result


# ------------------------------------------------------------
# Dependency detection
# ------------------------------------------------------------

def collect_project_text(files, archive):
    chunks = []
    total = 0

    for file in files:
        if is_ignored(file) or extension(file) not in SOURCE_EXTENSIONS:
            continue
        content = read_text_from_zip(archive, file, MAX_CODE_FILE)
        if not content:
            continue
        chunks.append(content)
        total += len(content)
        if total >= MAX_TOTAL_PROJECT_TEXT:
            break

    return "\n".join(chunks)


def detect_dependencies(files, archive):
    text = collect_project_text(files, archive)
    lowered = text.lower()

    dependencies = {
        "databases": [],
        "queues": [],
        "caches": [],
        "object_storage": [],
        "external_services": [],
    }
    evidence = {
        "databases": {},
        "queues": {},
        "caches": {},
        "object_storage": {},
    }

    for category, patterns in DATABASE_PATTERNS.items():
        matches = sorted(p for p in patterns if p in lowered)
        if matches:
            dependencies["databases"].append(category)
            evidence["databases"][category] = matches[:8]

    for category, patterns in QUEUE_PATTERNS.items():
        matches = sorted(p for p in patterns if p in lowered)
        if matches:
            dependencies["queues"].append(category)
            evidence["queues"][category] = matches[:8]

    for category, patterns in CACHE_PATTERNS.items():
        matches = sorted(p for p in patterns if p in lowered)
        if matches:
            dependencies["caches"].append(category)
            evidence["caches"][category] = matches[:8]

    for category, patterns in STORAGE_PATTERNS.items():
        matches = sorted(p for p in patterns if p in lowered)
        if matches:
            dependencies["object_storage"].append(category)
            evidence["object_storage"][category] = matches[:8]

    urls = set()
    for match in URL_PATTERN.findall(text):
        try:
            host = urlparse(match).hostname
            if host and host not in {"localhost", "127.0.0.1", "::1"}:
                # Do not call arbitrary URL-looking strings "dependencies"
                # unless they have a hostname.
                urls.add(host)
        except Exception:
            pass

    dependencies["external_services"] = sorted(urls)[:100]
    return dependencies, evidence


def detect_service_health(services, files, archive):
    result = {}

    for service in services:
        candidates = service_files(files, service.get("directory", ""))
        for file in candidates:
            if extension(file) not in CODE_EXTENSIONS:
                continue
            text = read_text_from_zip(archive, file, 350_000)
            matches = HEALTH_ROUTE_PATTERN.findall(text)
            if matches:
                result[service["name"]] = matches[0]
                break

    return result


def detect_health_endpoints(files, archive):
    endpoints = set()
    for file in files:
        if extension(file) not in CODE_EXTENSIONS:
            continue
        text = read_text_from_zip(archive, file, MAX_CODE_FILE)
        endpoints.update(HEALTH_ROUTE_PATTERN.findall(text))
    return sorted(endpoints)


def detect_ports(files, archive):
    ports = set()

    for file in files:
        name = basename(file)
        if is_ignored(file):
            continue
        if not (
            extension(file) in SOURCE_EXTENSIONS
            or is_dockerfile_name(name)
        ):
            continue

        content = read_text_from_zip(archive, file, 400_000)
        for pattern in PORT_PATTERNS:
            for match in pattern.findall(content):
                try:
                    port = int(match)
                    if 1 <= port <= 65535:
                        ports.add(port)
                except (TypeError, ValueError):
                    pass

    return sorted(ports)


def detect_environment(files, archive):
    env_files = []
    variables = []
    potential_secrets = []

    for file in files:
        name = basename(file)
        if not (
            name == ".env"
            or name.startswith(".env.")
            or name.endswith(".env")
        ):
            continue

        env_files.append(file)
        content = read_text_from_zip(archive, file, 300_000)

        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue

            variables.append(key)

            if SECRET_NAME_PATTERN.search(key):
                potential_secrets.append({
                    "file": file,
                    "variable": key,
                    "value_exposed": bool(value.strip()),
                })

    return {
        "files": unique(env_files),
        "variables": unique(variables),
        "potential_secrets": potential_secrets,
    }


# ------------------------------------------------------------
# CI/CD / IaC / deployment evidence
# ------------------------------------------------------------

def detect_ci_cd(files):
    results = []

    for file in files:
        path = clean_path(file).lower()
        name = basename(path)

        if (
            path.startswith(".github/workflows/")
            or path.startswith(".gitlab-ci")
            or path.startswith(".circleci/")
            or name in CI_BASENAMES
        ):
            results.append(file)

    return unique(results)


def detect_iac(files):
    results = []

    for file in files:
        name = basename(file)
        if (
            name.endswith(".tf")
            or name in {
                "pulumi.yaml", "pulumi.yml",
                "serverless.yml", "serverless.yaml"
            }
        ):
            results.append(file)

    return unique(results)


def detect_docker(files):
    return [f for f in files if is_dockerfile_name(basename(f))]


def detect_zerops(files):
    return [
        f for f in files
        if basename(f) in {"zerops.yml", "zerops.yaml"}
    ]


# ------------------------------------------------------------
# Dependency graph
#
# IMPORTANT:
# We do NOT connect every frontend to every backend.
# Connections require evidence:
#   1. Compose depends_on
#   2. A URL/host/port reference in source/config
#   3. A service environment variable points at another service
#   4. Explicit Kubernetes service references where detectable
# ------------------------------------------------------------

def service_ports(service):
    return set(service.get("ports", []))


def source_for_service(service, files, archive):
    chunks = []
    for file in service_files(files, service.get("directory", ""))[:200]:
        if extension(file) in SOURCE_EXTENSIONS:
            chunks.append(read_text_from_zip(archive, file, 250_000))
    return "\n".join(chunks)


def explicit_host_references(service, files, archive):
    text = source_for_service(service, files, archive)

    hosts = set()
    ports = set()

    for url in URL_PATTERN.findall(text):
        try:
            parsed = urlparse(url)
            if parsed.hostname:
                hosts.add(parsed.hostname.lower())
            if parsed.port:
                ports.add(parsed.port)
        except ValueError:
            pass

    # Also detect bare service-host style strings:
    # http://service:3000 is covered by URL_PATTERN.
    # HOST=service and SERVICE_URL=http://service are captured below.
    for match in re.finditer(
        r"\b(?:HOST|BASE_URL|SERVICE_URL|API_URL|BACKEND_URL|"
        r"FRONTEND_URL|ENDPOINT)\s*[:=]\s*[\"']?([A-Za-z0-9_.-]+)",
        text,
        re.I,
    ):
        hosts.add(match.group(1).lower())

    return hosts, ports


def build_dependency_graph(services, compose_services, aliases, files, archive):
    nodes = [
        {
            "name": s["name"],
            "type": s["type"],
            "technology": s["technology"],
            "replicas": s.get("declared_replicas", 1),
        }
        for s in services
    ]

    connections = []

    canonical = {s["name"].lower(): s["name"] for s in services}
    by_port = {}
    for service in services:
        for port in service_ports(service):
            by_port.setdefault(port, []).append(service["name"])

    def add_edge(source, target, relationship, inference, confidence="medium"):
        source = resolve_alias(source, aliases)
        target = resolve_alias(target, aliases)
        if source == target:
            return
        if source not in canonical.values() or target not in canonical.values():
            return
        connections.append({
            "from": source,
            "to": target,
            "relationship": relationship,
            "inference": inference,
            "confidence": confidence,
        })

    # Strongest evidence: Compose depends_on.
    for compose in compose_services:
        source = resolve_alias(compose["name"], aliases)
        for dependency in compose.get("depends_on", []):
            target = resolve_alias(dependency, aliases)
            add_edge(
                source,
                target,
                "depends_on",
                "Docker Compose depends_on",
                "high",
            )

    # Code/config references to another service by host or port.
    for service in services:
        hosts, referenced_ports = explicit_host_references(service, files, archive)

        for other in services:
            if other["name"] == service["name"]:
                continue

            other_name = other["name"].lower()
            other_aliases = {
                str(other.get("name", "")).lower(),
                *[str(x).lower() for x in other.get("compose_names", [])],
            }

            host_match = bool(hosts.intersection(other_aliases))
            port_match = bool(referenced_ports.intersection(service_ports(other)))

            if host_match:
                add_edge(
                    service["name"],
                    other["name"],
                    "request",
                    "service hostname/reference detected in source",
                    "high",
                )
            elif port_match:
                add_edge(
                    service["name"],
                    other["name"],
                    "request",
                    "referenced port matches detected service port",
                    "medium",
                )

        # External URL is represented separately, not as a fake service.
    return {
        "nodes": unique(nodes),
        "connections": unique(connections),
    }


# ------------------------------------------------------------
# Reliability analysis
# ------------------------------------------------------------

def make_finding(severity, category, title, description, recommendation, score_impact):
    return {
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "recommendation": recommendation,
        "score_impact": score_impact,
    }


def analyze_reliability(
    services,
    dependencies,
    health_endpoints,
    service_health,
    dockerfiles,
    zerops_configs,
    compose_services,
    k8s_workloads,
    env_info,
    ci_cd,
    iac,
    architecture,
):
    findings = []

    # Replica findings are based only on actual deployment evidence.
    for service in services:
        replicas = service.get("declared_replicas", 1)

        if service["type"] in {"backend", "frontend"} and replicas < 2:
            severity = "critical" if service["type"] == "backend" else "warning"
            impact = 20 if severity == "critical" else 8

            findings.append(make_finding(
                severity,
                "availability",
                f"{service['name']} Single Instance Detected",
                f"Static deployment evidence represents {service['name']} with {replicas} instance(s).",
                f"Consider running at least 2 instances behind health-aware routing when the workload requires high availability.",
                impact,
            ))

        elif service["type"] == "worker" and replicas < 2:
            findings.append(make_finding(
                "warning",
                "availability",
                f"{service['name']} Worker Redundancy Not Detected",
                f"No redundant {service['name']} worker instances were detected.",
                "Run multiple workers where workload semantics permit and use durable queue/retry semantics.",
                8,
            ))

    # Health checks: distinguish application health detection from
    # deployment configuration. A route in source is not automatically
    # a configured platform health check.
    if not health_endpoints:
        findings.append(make_finding(
            "warning",
            "observability",
            "Health Endpoint Not Detected",
            "No common application health/readiness endpoint was detected.",
            "Expose a service-appropriate health/readiness endpoint and configure the deployment to use it.",
            8,
        ))
    else:
        missing = [
            s["name"]
            for s in services
            if s["type"] in {"backend", "worker"}
            and s["name"] not in service_health
        ]
        if missing:
            findings.append(make_finding(
                "warning",
                "observability",
                "Some Services Lack Service-Specific Health Checks",
                "Health endpoints exist in the project, but not every backend/worker service has a route detected inside its own source scope.",
                "Add service-specific health/readiness checks where appropriate.",
                5,
            ))

    # Dependency availability cannot be proven statically.
    for database in dependencies["databases"]:
        findings.append(make_finding(
            "warning",
            "data",
            f"{database} Availability Requires Review",
            f"{database} was detected as an application dependency, but static analysis cannot determine its replication or failover configuration.",
            "Review backups, replication, failover, connection pooling and recovery requirements.",
            5,
        ))

    if any(s["type"] == "worker" for s in services) and not dependencies["queues"]:
        findings.append(make_finding(
            "warning",
            "async",
            "Worker Queue Not Detected",
            "Worker-like application code was detected without an obvious durable messaging dependency.",
            "Consider durable queueing, retries and dead-letter handling where asynchronous work is required.",
            6,
        ))

    # Correctly report containerization if ANY supported evidence exists.
    if not dockerfiles and not compose_services and not k8s_workloads:
        findings.append(make_finding(
            "info",
            "deployment",
            "Container / Orchestration Configuration Not Detected",
            "No Dockerfile, Compose service definition or Kubernetes workload was detected.",
            "Add explicit deployment configuration if reproducible containerized deployment is required.",
            2,
        ))

    if not ci_cd:
        findings.append(make_finding(
            "info",
            "delivery",
            "CI/CD Configuration Not Detected",
            "No recognized CI/CD workflow was detected.",
            "Add automated build, test and deployment checks before production rollout.",
            2,
        ))

    if not iac:
        findings.append(make_finding(
            "info",
            "infrastructure",
            "Infrastructure-as-Code Not Detected",
            "No recognized Terraform, Pulumi or serverless infrastructure definition was detected.",
            "Consider versioning infrastructure configuration as infrastructure complexity grows.",
            1,
        ))

    if zerops_configs:
        findings.append(make_finding(
            "info",
            "deployment",
            "Existing Zerops Configuration Detected",
            "A Zerops configuration file already exists in the uploaded project.",
            "Compare the existing configuration with the generated analysis before replacing it.",
            0,
        ))

    exposed = [
        x for x in env_info["potential_secrets"]
        if x["value_exposed"]
    ]
    if exposed:
        findings.append(make_finding(
            "critical",
            "security",
            "Potential Secrets Found in Environment Files",
            f"{len(exposed)} secret-like variables appear to contain values in uploaded files.",
            "Do not commit real credentials. Rotate exposed credentials and use deployment secret management.",
            20,
        ))

    if not services:
        findings.append(make_finding(
            "critical",
            "analysis",
            "Application Service Could Not Be Identified",
            "The analyzer could not confidently identify an application service from the archive.",
            "Provide a supported manifest, Docker/Compose configuration or recognizable application source.",
            30,
        ))

    return findings


def calculate_score(findings):
    # Score is a static risk indicator, not a measured uptime percentage.
    score = 100
    for finding in findings:
        score -= int(finding.get("score_impact", 0))
    return max(0, min(100, score))


def calculate_risk_summary(findings):
    counts = {"critical": 0, "warning": 0, "info": 0}

    for finding in findings:
        severity = finding.get("severity")
        if severity in counts:
            counts[severity] += 1

    if counts["critical"]:
        level = "critical"
    elif counts["warning"] >= 3:
        level = "high"
    elif counts["warning"]:
        level = "moderate"
    else:
        level = "low"

    return {
        "level": level,
        "critical": counts["critical"],
        "warning": counts["warning"],
        "info": counts["info"],
    }


# ------------------------------------------------------------
# Bottlenecks
# ------------------------------------------------------------

def detect_bottlenecks(services, dependencies, findings, architecture):
    candidates = []

    incoming = {s["name"]: 0 for s in services}
    outgoing = {s["name"]: 0 for s in services}

    for edge in architecture["connections"]:
        source = edge["from"]
        target = edge["to"]
        if source in outgoing:
            outgoing[source] += 1
        if target in incoming:
            incoming[target] += 1

    for service in services:
        replicas = service.get("declared_replicas", 1)
        degree = incoming.get(service["name"], 0) + outgoing.get(service["name"], 0)

        if degree:
            priority = min(95, 40 + degree * 10 + (25 if replicas < 2 else 0))
            candidates.append({
                "component": service["name"],
                "type": "service",
                "risk": "high" if replicas < 2 else "medium",
                "reason": (
                    f"Detected dependency graph degree is {degree}; "
                    f"static deployment evidence reports {replicas} instance(s)."
                ),
                "priority": priority,
            })

    for database in dependencies["databases"]:
        candidates.append({
            "component": database,
            "type": "database",
            "risk": "high",
            "reason": "Detected database dependency may constrain availability or throughput.",
            "priority": 80,
        })

    for queue in dependencies["queues"]:
        candidates.append({
            "component": queue,
            "type": "queue",
            "risk": "medium",
            "reason": "Messaging infrastructure can become a throughput or backlog bottleneck.",
            "priority": 65,
        })

    for cache in dependencies["caches"]:
        candidates.append({
            "component": cache,
            "type": "cache",
            "risk": "medium",
            "reason": "Cache saturation or failure can increase latency and dependency load.",
            "priority": 55,
        })

    for finding in findings:
        if finding["severity"] == "critical":
            candidates.append({
                "component": finding["title"],
                "type": "finding",
                "risk": "critical",
                "reason": finding["description"],
                "priority": 90,
            })

    candidates.sort(key=lambda x: x["priority"], reverse=True)
    return unique(candidates)[:10]


# ------------------------------------------------------------
# Optimization
# ------------------------------------------------------------

def build_optimization_plan(services, dependencies, deployment):
    actions = []

    for service in services:
        replicas = service.get("declared_replicas", 1)

        if service["type"] in {"backend", "worker", "frontend"} and replicas < 2:
            actions.append({
                "priority": "high" if service["type"] == "backend" else "medium",
                "service": service["name"],
                "action": "Increase redundancy",
                "current": f"{replicas} statically detected instance(s)",
                "recommended": "2+ instances where high availability is required",
                "reason": "Reduces the impact of a single instance failure.",
            })

        if (
            service["type"] in {"backend", "worker"}
            and service["name"] not in deployment.get("service_health", {})
        ):
            actions.append({
                "priority": "medium",
                "service": service["name"],
                "action": "Add health/readiness checks",
                "current": "No service-specific health endpoint detected",
                "recommended": "A service-appropriate health/readiness endpoint",
                "reason": "Allows unhealthy instances to be removed from traffic.",
            })

    if dependencies["databases"]:
        actions.append({
            "priority": "high",
            "service": "database layer",
            "action": "Review database high availability",
            "current": ", ".join(dependencies["databases"]),
            "recommended": "Backups + replication/failover appropriate to workload",
            "reason": "Application redundancy does not remove a database dependency.",
        })

    if any(s["type"] == "worker" for s in services) and not dependencies["queues"]:
        actions.append({
            "priority": "medium",
            "service": "worker infrastructure",
            "action": "Review durable queueing",
            "current": "No queue detected",
            "recommended": "Durable queue + retry/dead-letter strategy where applicable",
            "reason": "Separates producers from background consumers.",
        })

    if not deployment.get("ci_cd"):
        actions.append({
            "priority": "low",
            "service": "delivery",
            "action": "Add CI/CD validation",
            "current": "No CI/CD configuration detected",
            "recommended": "Automated build + test + deployment checks",
            "reason": "Prevents known problems from reaching production.",
        })

    if not deployment.get("iac"):
        actions.append({
            "priority": "low",
            "service": "infrastructure",
            "action": "Consider Infrastructure-as-Code",
            "current": "No supported IaC definition detected",
            "recommended": "Terraform/Pulumi/serverless configuration where appropriate",
            "reason": "Makes infrastructure changes reproducible.",
        })

    return actions


# ------------------------------------------------------------
# Failure simulator
# ------------------------------------------------------------

def build_failure_scenarios(services, dependencies):
    scenarios = []

    for service in services:
        scenarios.append({
            "id": f"service:{service['name']}",
            "type": "service_failure",
            "target": service["name"],
            "label": f"{service['name']} Failure",
            "description": f"Simulate failure of the {service['name']} service.",
        })

    for database in dependencies["databases"]:
        scenarios.append({
            "id": f"database:{database}",
            "type": "database_failure",
            "target": database,
            "label": f"{database} Failure",
            "description": f"Simulate loss of the detected {database} dependency.",
        })

    for queue in dependencies["queues"]:
        scenarios.append({
            "id": f"queue:{queue}",
            "type": "queue_failure",
            "target": queue,
            "label": f"{queue} Failure",
            "description": f"Simulate loss of the detected {queue} messaging layer.",
        })

    for cache in dependencies["caches"]:
        scenarios.append({
            "id": f"cache:{cache}",
            "type": "cache_failure",
            "target": cache,
            "label": f"{cache} Failure",
            "description": f"Simulate loss of the detected {cache} cache layer.",
        })

    scenarios.extend([
        {
            "id": "traffic",
            "type": "traffic_spike",
            "target": "all",
            "label": "Traffic Spike ×10",
            "description": "Simulate a tenfold increase in incoming traffic.",
        },
        {
            "id": "cascading",
            "type": "cascading_failure",
            "target": "critical-path",
            "label": "Cascading Failure",
            "description": "Simulate failure propagation through the inferred dependency graph.",
        },
    ])

    return scenarios


def simulate_failure(target, architecture, services):
    edges = architecture["connections"]

    # Reverse graph: if A -> B, failure of B can affect A.
    reverse = {}
    for edge in edges:
        reverse.setdefault(edge["to"], []).append(edge["from"])

    affected = []
    queue = [target]
    seen = {target}

    while queue:
        current = queue.pop(0)
        for dependent in reverse.get(current, []):
            if dependent not in seen:
                seen.add(dependent)
                affected.append(dependent)
                queue.append(dependent)

    target_service = next(
        (s for s in services if s["name"] == target),
        None,
    )

    target_replicas = target_service.get("declared_replicas", 1) if target_service else 1
    root_survives = target_replicas >= 2

    impact = len(affected)
    if root_survives:
        reliability = max(60, 100 - impact * 10)
    else:
        reliability = max(20, 80 - impact * 15)

    return {
        "reliability": reliability,
        "root_available": root_survives,
        "affected_services": affected,
        "impact_count": impact,
    }


# ------------------------------------------------------------
# Zerops configuration generation
#
# This is a deployment recommendation, not a claim that the
# generated file is universally valid for every Zerops runtime.
# Commands, ports and health paths come from detected evidence.
# ------------------------------------------------------------

def zerops_runtime(service):
    tech = (service.get("technology") or "").lower()

    if "python" in tech:
        return "python@latest"
    if "node.js" in tech or "nodejs" in tech or "javascript" in tech:
        return "nodejs@latest"
    if "java" in tech:
        return "java@latest"
    if "go" in tech:
        return "go@latest"
    if "rust" in tech:
        return "rust@latest"
    return "docker@latest"


def yaml_quote(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def generate_zerops_config(services, service_evidence, service_health):
    lines = [
        "# Generated by Zerops Autopilot",
        "# Static-analysis recommendation. Review runtime, commands, ports and health checks before deployment.",
        "",
        "zerops:",
    ]

    for service in services:
        name = service["name"]
        evidence = service_evidence.get(name, {})
        runtime = zerops_runtime(service)
        replicas = max(1, int(service.get("declared_replicas", 1)))

        lines.append("")
        lines.append(f"  - setup: {name}")
        lines.append("    run:")
        lines.append(f"      base: {runtime}")

        ports = unique(
            service.get("ports", [])
            + evidence.get("docker", {}).get("expose", [])
        )
        if ports:
            lines.append("      ports:")
            for port in ports:
                lines.append(f"        - port: {port}")
                lines.append("          protocol: TCP")
                lines.append("          httpSupport: true")

        build = evidence.get("build_command")
        start = evidence.get("start_command")

        if build:
            lines.append(f"      build: {build}")

        if start:
            lines.append(f"      start: {start}")
        else:
            lines.append(
                "      # start: not generated because no production start command was detected"
            )

        health = service_health.get(name)
        if health:
            port = ports[0] if ports else None
            if port:
                lines.append("      healthCheck:")
                lines.append("        httpGet:")
                lines.append(f"          port: {port}")
                lines.append(f"          path: {yaml_quote(health)}")

        if replicas > 1:
            lines.append(f"      replicas: {replicas}")

    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------
# Summaries
# ------------------------------------------------------------

def build_summary(
    services,
    technologies,
    dependencies,
    score,
    risk_summary,
    bottlenecks,
):
    return {
        "headline": (
            "Architecture requires reliability improvements"
            if risk_summary["critical"] or risk_summary["warning"]
            else "Architecture appears structurally healthy"
        ),
        "reliability_score": score,
        "risk_level": risk_summary["level"],
        "service_counts": {
            "frontend": sum(s["type"] == "frontend" for s in services),
            "backend": sum(s["type"] == "backend" for s in services),
            "worker": sum(s["type"] == "worker" for s in services),
        },
        "technology_count": len(technologies),
        "database_count": len(dependencies["databases"]),
        "queue_count": len(dependencies["queues"]),
        "cache_count": len(dependencies["caches"]),
        "object_storage_count": len(dependencies["object_storage"]),
        "top_bottleneck": bottlenecks[0]["component"] if bottlenecks else None,
    }


# ------------------------------------------------------------
# API
# ------------------------------------------------------------

@app.get("/")
def home():
    return jsonify({
        "service": "Zerops Autopilot Analyzer",
        "status": "running",
        "version": VERSION,
        "mode": "static-analysis",
        "ai_required": False,
        "database_required": False,
    })


@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "zerops-autopilot-analyzer",
        "version": VERSION,
    })


@app.post("/analyze-project")
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
                files = []
                for name in archive.namelist():
                    cleaned = clean_path(name)
                    if not name.endswith("/") and cleaned and not is_ignored(cleaned):
                        files.append(cleaned)

                files = unique(files)

                technologies = detect_technologies(files, archive)

                compose_files = detect_compose_files(files)
                compose_services = parse_compose_services(archive, compose_files)

                kubernetes_files = detect_kubernetes_files(files, archive)
                k8s_workloads = parse_kubernetes_workloads(kubernetes_files, archive)

                services, aliases = detect_services(
                    files,
                    archive,
                    compose_services,
                    k8s_workloads,
                )

                dependencies, dependency_evidence = detect_dependencies(
                    files,
                    archive,
                )

                ports = detect_ports(files, archive)
                health_endpoints = detect_health_endpoints(files, archive)
                service_health = detect_service_health(services, files, archive)

                dockerfiles = detect_docker(files)
                zerops_configs = detect_zerops(files)
                ci_cd = detect_ci_cd(files)
                iac = detect_iac(files)
                env_info = detect_environment(files, archive)

                # Derive deployment evidence once and reuse it everywhere.
                service_evidence = {}
                for service in services:
                    service_evidence[service["name"]] = infer_service_commands(
                        service,
                        files,
                        archive,
                    )

                    # Ports can be learned from Dockerfile EXPOSE.
                    docker = service_evidence[service["name"]].get("docker") or {}
                    service["ports"] = unique(
                        service.get("ports", []) + docker.get("expose", [])
                    )

                architecture = build_dependency_graph(
                    services,
                    compose_services,
                    aliases,
                    files,
                    archive,
                )

                findings = analyze_reliability(
                    services=services,
                    dependencies=dependencies,
                    health_endpoints=health_endpoints,
                    service_health=service_health,
                    dockerfiles=dockerfiles,
                    zerops_configs=zerops_configs,
                    compose_services=compose_services,
                    k8s_workloads=k8s_workloads,
                    env_info=env_info,
                    ci_cd=ci_cd,
                    iac=iac,
                    architecture=architecture,
                )

                reliability_score = calculate_score(findings)
                risk_summary = calculate_risk_summary(findings)

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
                    "environment_files": env_info["files"],
                    "containerization_detected": bool(
                        dockerfiles or compose_services or k8s_workloads
                    ),
                }

                bottlenecks = detect_bottlenecks(
                    services,
                    dependencies,
                    findings,
                    architecture,
                )

                optimization_plan = build_optimization_plan(
                    services,
                    dependencies,
                    deployment,
                )

                zerops_yml = generate_zerops_config(
                    services,
                    service_evidence,
                    service_health,
                )

                failure_scenarios = build_failure_scenarios(
                    services,
                    dependencies,
                )

                summary = build_summary(
                    services,
                    technologies,
                    dependencies,
                    reliability_score,
                    risk_summary,
                    bottlenecks,
                )

                response = {
                    "status": "success",
                    "analyzer": {
                        "name": "Zerops Autopilot Analyzer",
                        "version": VERSION,
                        "mode": "static-analysis",
                        "ai_required": False,
                        "database_required": False,
                    },
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
                        "potential_secrets": env_info["potential_secrets"],
                    },
                    "compose_services": compose_services,
                    "kubernetes_workloads": k8s_workloads,
                    "service_evidence": service_evidence,
                    "architecture": architecture,
                    "failure_scenarios": failure_scenarios,
                    "reliability_score": reliability_score,
                    "risk_summary": risk_summary,
                    "findings": findings,
                    "bottlenecks": bottlenecks,
                    "optimization_plan": optimization_plan,
                    "zeropsYml": zerops_yml,
                    "files": files[:500],
                }

                app.logger.info(
                    "Analyzed %s: %d files, %d services, reliability=%d, risk=%s",
                    project.filename,
                    len(files),
                    len(services),
                    reliability_score,
                    risk_summary["level"],
                )

                return jsonify(response)

        except zipfile.BadZipFile:
            return jsonify({"error": "The uploaded ZIP file is corrupted"}), 400

        except Exception as error:
            app.logger.exception("Project analysis failed")
            return jsonify({
                "error": "Project analysis failed",
                "details": str(error),
            }), 500


if __name__ == "__main__":
    # debug=False is safer for a deployment build.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
