from flask import Flask, request, jsonify


import zipfile


import os


import tempfile


import re


import json


from urllib.parse import urlparse


app = Flask(__name__)


VERSION = "5.0"


IGNORED_DIRECTORIES = {
    "node_modules", ".git", ".next", "dist", "build",
    "__pycache__", ".venv", "venv", "coverage",
    ".pytest_cache", ".idea", ".vscode", ".turbo",
    ".cache", ".parcel-cache", "target", "vendor"
}


FRONTEND_NAMES = {
    "frontend", "client", "web", "ui", "frontend-app",
    "website", "dashboard", "portal"
}


BACKEND_NAMES = {
    "backend", "server", "api", "service", "backend-api",
    "services", "app-server"
}


WORKER_NAMES = {
    "worker", "workers", "job", "jobs", "queue", "queues",
    "notification", "notifications", "processor", "processing",
    "task", "tasks", "consumer", "consumers", "scheduler",
    "cron", "worker-service"
}


SOURCE_EXTENSIONS = (
    ".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs",
    ".rb", ".php", ".cs", ".json", ".yml", ".yaml", ".toml",
    ".env", ".txt", ".properties", ".ini", ".xml"
)


CODE_EXTENSIONS = (
    ".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs",
    ".rb", ".php", ".cs"
)


HEALTH_ROUTE_PATTERN = re.compile(
    r'["\'](/(?:api/)?(?:health|healthz|ready|readiness|live|liveness))["\']',
    flags=re.IGNORECASE
)


PORT_PATTERNS = [
    r"\bPORT\s*=\s*[\"']?(\d{2,5})",
    r"\bport\s*[:=]\s*[\"']?(\d{2,5})",
    r"\blisten\s*\(\s*[\"']?(\d{2,5})",
    r"\bEXPOSE\s+(\d{2,5})",
    r"\b--port[=\s]+(\d{2,5})",
]


FRAMEWORK_RULES = {
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


DATABASE_PATTERNS = {
    "PostgreSQL": ["postgres", "postgresql", "psycopg", "asyncpg"],
    "MySQL": ["mysql", "mysql2", "pymysql"],
    "MongoDB": ["mongodb", "mongoose", "pymongo"],
    "Redis": ["redis", "ioredis", "redis-py"],
    "SQLite": ["sqlite", "sqlite3"],
    "MariaDB": ["mariadb"],
    "Cassandra": ["cassandra"],
    "DynamoDB": ["dynamodb", "boto3"],
}


QUEUE_PATTERNS = {
    "RabbitMQ": ["rabbitmq", "amqp", "pika"],
    "Kafka": ["kafka", "confluent-kafka"],
    "BullMQ": ["bullmq"],
    "Bull": ["bull"],
    "Celery": ["celery"],
    "AWS SQS": ["sqs"],
    "Google Pub/Sub": ["pubsub"],
}


CACHE_PATTERNS = {
    "Redis": ["redis", "ioredis", "redis-py"],
    "Memcached": ["memcached"],
}


STORAGE_PATTERNS = {
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


def clean_path(path):
    path = str(path).replace("\\", "/")
    path = re.sub(r"^\./+", "", path)
    return path.strip("/")


def is_ignored(path):
    parts = clean_path(path).split("/")
    return any(part.lower() in IGNORED_DIRECTORIES for part in parts)


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
        key = (
            json.dumps(item, sort_keys=True)
            if isinstance(item, dict)
            else str(item)
        )

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def path_is_inside(path, directory):
    path = clean_path(path)
    directory = clean_path(directory).strip("/")

    if not directory:
        return "/" not in path

    return path == directory or path.startswith(directory + "/")


def get_directories(files):
    directories = {}

    for file in files:
        if is_ignored(file):
            continue

        parts = clean_path(file).split("/")

        if len(parts) <= 1:
            continue

        for index in range(1, len(parts)):
            directory_path = "/".join(parts[:index])

            directories.setdefault(
                directory_path,
                []
            ).append(file)

    return directories


def directory_name(path):
    return clean_path(path).split("/")[-1]


def read_package_json(archive, file):
    return safe_json(
        read_text_from_zip(archive, file)
    )


def detect_manifest_type(directory_files):
    names = {
        basename(file)
        for file in directory_files
    }

    if "package.json" in names:
        return "Node.js"

    if names.intersection({
        "requirements.txt",
        "pyproject.toml",
        "pipfile"
    }):
        return "Python"

    if names.intersection({
        "pom.xml",
        "build.gradle",
        "build.gradle.kts"
    }):
        return "Java"

    if "go.mod" in names:
        return "Go"

    if "cargo.toml" in names:
        return "Rust"

    if "gemfile" in names:
        return "Ruby"

    if "composer.json" in names:
        return "PHP"

    if any(name.endswith(".csproj") for name in names):
        return "C#"

    if names.intersection({
        "dockerfile",
        "containerfile"
    }):
        return "Container"

    return "Unknown"


def detect_frameworks(directory_files, archive):
    frameworks = []

    package_files = [
        file
        for file in directory_files
        if basename(file) == "package.json"
    ]

    for package_file in package_files:
        package = read_package_json(
            archive,
            package_file
        )

        dependencies = {}

        dependencies.update(
            package.get("dependencies", {}) or {}
        )

        dependencies.update(
            package.get("devDependencies", {}) or {}
        )

        dependency_names = {
            str(key).lower()
            for key in dependencies.keys()
        }

        for framework, rules in FRAMEWORK_RULES.items():

            if any(
                rule.lower() in dependency_names
                for rule in rules
            ):
                frameworks.append(
                    framework
                )

    text = ""

    for file in directory_files:

        if file.lower().endswith(
            CODE_EXTENSIONS
        ):
            text += "\n" + read_text_from_zip(
                archive,
                file,
                400_000
            ).lower()

    text_rules = {

        "FastAPI": [
            "from fastapi",
            "import fastapi"
        ],

        "Flask": [
            "from flask",
            "import flask"
        ],

        "Django": [
            "django"
        ],

        "Spring Boot": [
            "springboot",
            "spring boot"
        ]

    }

    for framework, rules in text_rules.items():

        if any(
            rule in text
            for rule in rules
        ):
            frameworks.append(
                framework
            )

    return unique(frameworks)


def detect_service_technology(
    directory_files,
    archive
):
    manifest = detect_manifest_type(
        directory_files
    )

    if manifest == "Node.js":

        frameworks = detect_frameworks(
            directory_files,
            archive
        )

        if frameworks:
            return (
                "Node.js / "
                + " + ".join(frameworks)
            )

        return "Node.js"

    if manifest == "Python":

        frameworks = detect_frameworks(
            directory_files,
            archive
        )

        if frameworks:
            return (
                "Python / "
                + " + ".join(frameworks)
            )

        return "Python"

    return manifest


def detect_compose_files(files):

    names = {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml"
    }

    return [
        file
        for file in files
        if basename(file) in names
    ]


def detect_kubernetes_files(
    files,
    archive
):

    result = []

    for file in files:

        if not file.lower().endswith(
            (".yml", ".yaml")
        ):
            continue

        text = read_text_from_zip(
            archive,
            file,
            700_000
        )

        if re.search(
            r"(?m)^\s*kind\s*:\s*"
            r"(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service)\s*$",
            text
        ):
            result.append(file)

    return result


def parse_kubernetes_workloads(
    files,
    archive
):

    workloads = []

    for file in files:

        if not file.lower().endswith(
            (".yml", ".yaml")
        ):
            continue

        text = read_text_from_zip(
            archive,
            file,
            1_500_000
        )

        kind_match = re.search(
            r"(?m)^\s*kind\s*:\s*"
            r"([A-Za-z0-9]+)\s*$",
            text
        )

        name_match = re.search(
            r"(?ms)metadata:\s*\n"
            r"(?:\s+[^\n]+\n)*?"
            r"\s+name\s*:\s*"
            r"([A-Za-z0-9_.-]+)",
            text
        )

        replicas_match = re.search(
            r"(?m)^\s*replicas\s*:\s*(\d+)\s*$",
            text
        )

        if (
            kind_match
            and name_match
        ):

            kind = kind_match.group(1)

            if kind in {
                "Deployment",
                "StatefulSet",
                "DaemonSet",
                "Job",
                "CronJob"
            }:

                workloads.append({

                    "name":
                        name_match.group(1),

                    "kind":
                        kind,

                    "replicas":
                        int(
                            replicas_match.group(1)
                        )
                        if replicas_match
                        else 1,

                    "file":
                        file

                })

    return workloads


def classify_directory(
    name,
    technology,
    directory_files,
    archive
):

    name_lower = name.lower()

    if name_lower in FRONTEND_NAMES:
        return "frontend"

    if name_lower in BACKEND_NAMES:
        return "backend"

    if name_lower in WORKER_NAMES:
        return "worker"

    frameworks = detect_frameworks(
        directory_files,
        archive
    )

    framework_text = (
        " ".join(frameworks)
        .lower()
    )

    if any(
        framework in framework_text
        for framework in (
            "react",
            "next.js",
            "vite",
            "vue",
            "angular",
            "svelte"
        )
    ):
        return "frontend"

    text = ""

    for file in directory_files[:80]:

        if file.lower().endswith(
            CODE_EXTENSIONS
        ):

            text += "\n" + read_text_from_zip(
                archive,
                file,
                150_000
            ).lower()

    if any(
        term in text
        for term in (
            "bullmq",
            "celery",
            "rq.worker",
            "consumer(",
            "kafkaconsumer",
            "rabbitmq",
            "background_tasks",
            "dramatiq"
        )
    ):
        return "worker"

    if technology != "Unknown":
        return "backend"

    return None


def collect_project_text(
    files,
    archive,
    max_total=12_000_000
):

    chunks = []
    total = 0

    for file in files:

        if is_ignored(file):
            continue

        if not file.lower().endswith(
            SOURCE_EXTENSIONS
        ):
            continue

        content = read_text_from_zip(
            archive,
            file,
            500_000
        )

        if not content:
            continue

        chunks.append(content)

        total += len(content)

        if total >= max_total:
            break

    return "\n".join(
        chunks
    ).lower()


def detect_environment(
    files,
    archive
):

    env_files = []
    variables = []
    potential_secrets = []

    recognized_env_names = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.example",
        ".env.sample"
    }

    for file in files:

        name = basename(file)

        if (
            name in recognized_env_names
            or name.startswith(".env")
            or name.endswith(".env")
        ):

            env_files.append(
                file
            )

            content = read_text_from_zip(
                archive,
                file,
                300_000
            )

            for raw in content.splitlines():

                line = raw.strip()

                if (
                    not line
                    or line.startswith("#")
                    or "=" not in line
                ):
                    continue

                key, _, value = (
                    line.partition("=")
                )

                key = key.strip()

                if not key:
                    continue

                variables.append(
                    key
                )

                if SECRET_NAME_PATTERNS.search(
                    key
                ):

                    potential_secrets.append({

                        "file":
                            file,

                        "variable":
                            key,

                        "value_exposed":
                            bool(
                                value.strip()
                            )

                    })

    return {

        "files":
            unique(env_files),

        "variables":
            unique(variables),

        "potential_secrets":
            potential_secrets

    }


def detect_ports(
    files,
    archive
):

    ports = set()

    for file in files:

        if is_ignored(file):
            continue

        if not file.lower().endswith(
            (
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".py",
                ".yml",
                ".yaml",
                ".env",
                ".dockerfile",
                "dockerfile",
                ".json"
            )
        ):
            continue

        content = read_text_from_zip(
            archive,
            file,
            500_000
        )

        for pattern in PORT_PATTERNS:

            for match in re.findall(
                pattern,
                content,
                flags=re.IGNORECASE
            ):

                try:

                    port = int(match)

                    if 1 <= port <= 65535:
                        ports.add(port)

                except ValueError:
                    pass

    return sorted(
        ports
    )


def detect_health_endpoints(
    files,
    archive
):

    endpoints = set()

    for file in files:

        if is_ignored(file):
            continue

        if not file.lower().endswith(
            CODE_EXTENSIONS
        ):
            continue

        content = read_text_from_zip(
            archive,
            file
        )

        endpoints.update(
            HEALTH_ROUTE_PATTERN.findall(
                content
            )
        )

    return sorted(
        endpoints
    )


def detect_zerops(files):

    return [
        file
        for file in files
        if basename(file)
        in {
            "zerops.yml",
            "zerops.yaml"
        }
    ]


def detect_ci_cd(files):

    results = []

    for file in files:

        path = clean_path(
            file
        ).lower()

        if (
            path.startswith(
                ".github/workflows/"
            )
            or path.startswith(
                ".gitlab-ci"
            )
            or basename(path)
            in {
                "jenkinsfile",
                "azure-pipelines.yml",
                "circleci"
            }
        ):

            results.append(
                file
            )

    return results


def detect_iac(files):

    results = []

    for file in files:

        name = basename(file)

        if (
            name.endswith(".tf")
            or name in {
                "pulumi.yaml",
                "pulumi.yml",
                "serverless.yml",
                "serverless.yaml"
            }
        ):

            results.append(
                file
            )

    return results


def build_failure_scenarios(
    services,
    dependencies
):

    scenarios = []

    for service in services:

        service_type = (
            "worker"
            if service["type"] == "worker"
            else service["type"]
        )

        scenarios.append({

            "id":
                service["name"],

            "type":
                "service_failure",

            "target":
                service["name"],

            "label":
                f"{service['name']} Failure",

            "description":
                f"Simulate failure of the "
                f"{service_type} service."

        })

    for database in dependencies[
        "databases"
    ]:

        scenarios.append({

            "id":
                f"database:{database}",

            "type":
                "database_failure",

            "target":
                database,

            "label":
                f"{database} Failure",

            "description":
                f"Simulate loss of the "
                f"{database} dependency."

        })

    for queue in dependencies[
        "queues"
    ]:

        scenarios.append({

            "id":
                f"queue:{queue}",

            "type":
                "queue_failure",

            "target":
                queue,

            "label":
                f"{queue} Failure",

            "description":
                f"Simulate loss of the "
                f"{queue} messaging layer."

        })

    for cache in dependencies[
        "caches"
    ]:

        scenarios.append({

            "id":
                f"cache:{cache}",

            "type":
                "cache_failure",

            "target":
                cache,

            "label":
                f"{cache} Failure",

            "description":
                f"Simulate loss of the "
                f"{cache} cache layer."

        })

    scenarios.append({

        "id":
            "traffic",

        "type":
            "traffic_spike",

        "target":
            "all",

        "label":
            "Traffic Spike ×10",

        "description":
            "Simulate a tenfold increase "
            "in incoming traffic."

    })

    scenarios.append({

        "id":
            "cascading",

        "type":
            "cascading_failure",

        "target":
            "critical-path",

        "label":
            "Cascading Failure",

        "description":
            "Simulate failure propagation "
            "through the inferred dependency graph."

    })

    return scenarios


def make_finding(
    severity,
    category,
    title,
    description,
    recommendation,
    score_impact
):

    return {

        "severity":
            severity,

        "category":
            category,

        "title":
            title,

        "description":
            description,

        "recommendation":
            recommendation,

        "score_impact":
            score_impact

    }


def calculate_risk_summary(
    findings
):

    counts = {
        "critical": 0,
        "warning": 0,
        "info": 0
    }

    for finding in findings:

        severity = finding.get(
            "severity"
        )

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

        "level":
            level,

        "critical":
            counts["critical"],

        "warning":
            counts["warning"],

        "info":
            counts["info"]

    }


def zerops_technology(
    service
):

    technology = (
        service.get(
            "technology"
        )
        or ""
    ).lower()

    if "python" in technology:
        return "python"

    if "java" in technology:
        return "java"

    if "go" in technology:
        return "go"

    if "rust" in technology:
        return "rust"

    return "nodejs"


def sanitize_yaml_value(
    value
):

    value = (
        str(value)
        .replace("\n", " ")
        .strip()
    )

    return value.replace(
        '"',
        '\\"'
    )


def build_summary(
    services,
    technologies,
    dependencies,
    score,
    risk_summary,
    bottlenecks
):

    service_counts = {

        "frontend":
            len([
                service
                for service in services
                if service["type"] == "frontend"
            ]),

        "backend":
            len([
                service
                for service in services
                if service["type"] == "backend"
            ]),

        "worker":
            len([
                service
                for service in services
                if service["type"] == "worker"
            ])

    }

    return {

        "headline":
            (
                "Architecture requires reliability improvements"
                if (
                    risk_summary["critical"]
                    or risk_summary["warning"]
                )
                else
                "Architecture appears structurally healthy"
            ),

        "reliability_score":
            score,

        "risk_level":
            risk_summary["level"],

        "service_counts":
            service_counts,

        "technology_count":
            len(technologies),

        "database_count":
            len(
                dependencies["databases"]
            ),

        "queue_count":
            len(
                dependencies["queues"]
            ),

        "cache_count":
            len(
                dependencies["caches"]
            ),

        "top_bottleneck":
            (
                bottlenecks[0]["component"]
                if bottlenecks
                else None
            )

    }


VERSION = "6.0"


def _direct_files(files, directory):
    directory = clean_path(directory).strip("/")
    if not directory or directory == ".":
        return [f for f in files if "/" not in f]
    prefix = directory + "/"
    return [f for f in files if f.startswith(prefix) and "/" not in f[len(prefix):]]


def _all_files_under(files, directory):
    directory = clean_path(directory).strip("/")
    if not directory or directory == ".":
        return [f for f in files if "/" not in f]
    prefix = directory + "/"
    return [f for f in files if f.startswith(prefix)]


def _manifest_data(archive, directory_files):
    for f in directory_files:
        if basename(f) == "package.json":
            data = read_package_json(archive, f)
            if data:
                return "Node.js", data, f
    names = {basename(f) for f in directory_files}
    if names.intersection({"requirements.txt", "pyproject.toml", "pipfile", "poetry.lock"}):
        return "Python", {}, next((f for f in directory_files if basename(f) in {"requirements.txt", "pyproject.toml", "pipfile"}), None)
    if names.intersection({"pom.xml", "build.gradle", "build.gradle.kts", "mvnw", "gradlew"}):
        return "Java", {}, next((f for f in directory_files if basename(f) in {"pom.xml", "build.gradle", "build.gradle.kts"}), None)
    if "go.mod" in names:
        return "Go", {}, next((f for f in directory_files if basename(f) == "go.mod"), None)
    if "cargo.toml" in names:
        return "Rust", {}, next((f for f in directory_files if basename(f) == "cargo.toml"), None)
    if "gemfile" in names:
        return "Ruby", {}, next((f for f in directory_files if basename(f) == "gemfile"), None)
    if "composer.json" in names:
        return "PHP", {}, next((f for f in directory_files if basename(f) == "composer.json"), None)
    if any(basename(f).endswith(".csproj") for f in directory_files):
        return ".NET", {}, next((f for f in directory_files if basename(f).endswith(".csproj")), None)
    return "Unknown", {}, None


def _frameworks_and_scripts(archive, directory_files):
    frameworks = set(detect_frameworks(directory_files, archive))
    package = {}
    package_file = None
    for f in directory_files:
        if basename(f) == "package.json":
            package = read_package_json(archive, f)
            package_file = f
            break
    deps = {}
    deps.update(package.get("dependencies", {}) or {})
    deps.update(package.get("devDependencies", {}) or {})
    dep_names = {str(k).lower() for k in deps}
    for framework, rules in FRAMEWORK_RULES.items():
        if any(str(rule).lower() in dep_names for rule in rules):
            frameworks.add(framework)
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    return sorted(frameworks), scripts, package, package_file


def _classify_dynamic(name, technology, frameworks, scripts, text, image=None):
    lname = name.lower()
    framework_text = " ".join(frameworks).lower()
    if any(x in framework_text for x in ("react", "next.js", "vite", "vue", "angular", "svelte")):
        return "frontend"
    if any(x in lname for x in WORKER_NAMES):
        return "worker"
    if any(token in text.lower() for token in (
        "celery", "bullmq", "rq.worker", "kafkaconsumer", "consumer(", "dramatiq", "background_tasks"
    )):
        return "worker"
    if "frontend" in lname or "client" in lname or "web" == lname:
        # Name is only a weak signal; manifests/code above take precedence.
        return "frontend"
    if technology != "Unknown" or image:
        return "backend"
    return None


def _compose_build_dir(item):
    build = item.get("build")
    if not build:
        return ""
    build = clean_path(str(build).strip("'\""))
    if build in (".", ""):
        return ""
    # Compose can use a mapping: context: ./dir. The legacy parser may store a raw value.
    return build


def _compose_service_type(item):
    image = (item.get("image") or "").lower()
    name = item.get("name", "").lower()
    if any(x in name for x in WORKER_NAMES):
        return "worker"
    if any(x in image for x in ("nginx", "caddy", "httpd")):
        return "frontend"
    return "backend"


def parse_compose_services(archive, compose_files):
    result = {}
    for file in compose_files:
        text = read_text_from_zip(archive, file, 2_000_000)
        lines = text.splitlines()
        in_services = False
        current = None
        block = None
        for raw in lines:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            stripped = raw.strip()
            if indent == 0 and stripped == "services:":
                in_services = True; current = None; block = None; continue
            if not in_services: continue
            if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
                current = stripped[:-1].strip().strip("'\"")
                result.setdefault(current, {"name": current, "file": file, "image": None, "build": None, "dockerfile": None, "ports": [], "depends_on": [], "replicas": None, "environment": [], "environment_values": {}})
                block = None; continue
            if not current or current not in result or indent < 4: continue
            entry = result[current]
            if indent == 4:
                block = None
                if stripped.startswith("image:"):
                    entry["image"] = stripped.split(":",1)[1].strip().strip("'\"")
                elif stripped == "build:" or stripped.startswith("build:"):
                    value = stripped.split(":",1)[1].strip()
                    entry["build"] = value.strip("'\"") if value else "."
                    block = "build"
                elif stripped == "ports:": block = "ports"
                elif stripped == "depends_on:": block = "depends_on"
                elif stripped == "environment:": block = "environment"
                elif stripped == "deploy:": block = "deploy"
                continue
            if block == "build" and indent >= 6:
                if stripped.startswith("context:"):
                    entry["build"] = stripped.split(":",1)[1].strip().strip("'\"")
                elif stripped.startswith("dockerfile:"):
                    entry["dockerfile"] = stripped.split(":",1)[1].strip().strip("'\"")
            elif block == "ports" and indent >= 6:
                m = re.search(r"(\d{2,5})(?::(\d{2,5}))?", stripped)
                if m:
                    # Host:container -> application listens on container port.
                    port = int(m.group(2) or m.group(1))
                    if 10 <= port <= 65535: entry["ports"].append(port)
            elif block == "depends_on" and indent >= 6:
                dep = stripped.lstrip("- ").strip().strip("'\"")
                if re.match(r"^[A-Za-z0-9_.-]+$", dep): entry["depends_on"].append(dep)
            elif block == "environment" and indent >= 6:
                value = stripped.lstrip("- ").strip().strip("'\"")
                if ":" in value:
                    key, val = value.split(":",1)
                    entry["environment"].append(key.strip())
                    entry["environment_values"][key.strip()] = val.strip().strip("'\"")
                elif "=" in value:
                    key, val = value.split("=",1)
                    entry["environment"].append(key.strip())
                    entry["environment_values"][key.strip()] = val.strip().strip("'\"")
            elif block == "deploy" and indent >= 8:
                m = re.match(r"replicas:\s*(\d+)", stripped)
                if m: entry["replicas"] = int(m.group(1))
    # Some Compose variants put build configuration in mappings; recover it from the raw text.
    for item in result.values():
        item["ports"] = unique(item["ports"]); item["depends_on"] = unique(item["depends_on"]); item["environment"] = unique(item["environment"])
    return list(result.values())


def _docker_named_files(files):
    result = []
    for f in files:
        n = basename(f)
        if n == "dockerfile" or n == "containerfile" or n.endswith(".dockerfile") or n.endswith(".containerfile"):
            result.append(f)
    return result


def detect_docker(files):
    return _docker_named_files(files)


def detect_technologies(files, archive):
    technologies = []
    names = {basename(f) for f in files}
    if "package.json" in names:
        technologies.append("Node.js / JavaScript")
    if names.intersection({"requirements.txt", "pyproject.toml", "pipfile", "poetry.lock"}):
        technologies.append("Python")
    if any(basename(f) in {"dockerfile", "containerfile"} or basename(f).endswith((".dockerfile", ".containerfile")) for f in files):
        technologies.append("Docker / OCI")
    if any(basename(f) in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"} for f in files):
        technologies.append("Docker Compose")
    if "pom.xml" in names or "build.gradle" in names or "build.gradle.kts" in names:
        technologies.append("Java")
    if "go.mod" in names:
        technologies.append("Go")
    if "cargo.toml" in names:
        technologies.append("Rust")
    if "gemfile" in names:
        technologies.append("Ruby")
    if "composer.json" in names:
        technologies.append("PHP")
    if any(basename(f).endswith(".csproj") for f in files):
        technologies.append(".NET")
    if any(clean_path(f).lower().startswith(".github/workflows/") for f in files):
        technologies.append("GitHub Actions")
    if any(clean_path(f).lower().startswith(".gitlab-ci") or basename(f).lower() == "jenkinsfile" for f in files):
        technologies.append("CI/CD")
    if detect_kubernetes_files(files, archive):
        technologies.append("Kubernetes")
    if detect_zerops(files):
        technologies.append("Zerops")
    return unique(technologies)


def _service_local_dependency_evidence(archive, files, directory):
    local = _all_files_under(files, directory)
    text_parts = []
    evidence = {"databases": {}, "queues": {}, "caches": {}, "object_storage": {}, "external_services": []}
    for f in local[:300]:
        if is_ignored(f) or not f.lower().endswith(SOURCE_EXTENSIONS):
            continue
        content = read_text_from_zip(archive, f, 350_000)
        if content:
            text_parts.append((f, content))
    for category, patterns in DATABASE_PATTERNS.items():
        hits = []
        for f, content in text_parts:
            low = content.lower()
            found = [p for p in patterns if p.lower() in low]
            if found:
                hits.append({"file": f, "patterns": found[:5]})
        if hits:
            evidence["databases"][category] = hits[:8]
    for category, patterns in QUEUE_PATTERNS.items():
        hits = []
        for f, content in text_parts:
            low = content.lower()
            found = [p for p in patterns if p.lower() in low]
            if found:
                hits.append({"file": f, "patterns": found[:5]})
        if hits:
            evidence["queues"][category] = hits[:8]
    for category, patterns in CACHE_PATTERNS.items():
        hits = []
        for f, content in text_parts:
            low = content.lower()
            found = [p for p in patterns if p.lower() in low]
            if found:
                hits.append({"file": f, "patterns": found[:5]})
        if hits:
            evidence["caches"][category] = hits[:8]
    for category, patterns in STORAGE_PATTERNS.items():
        hits = []
        for f, content in text_parts:
            low = content.lower()
            found = [p for p in patterns if p.lower() in low]
            if found:
                hits.append({"file": f, "patterns": found[:5]})
        if hits:
            evidence["object_storage"][category] = hits[:8]
    for f, content in text_parts:
        for url in re.findall(r"https?://[A-Za-z0-9._:-]+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?", content):
            try:
                host = urlparse(url).hostname
            except Exception:
                host = None
            if host and host not in {"localhost", "127.0.0.1", "0.0.0.0"}:
                evidence["external_services"].append({"host": host, "file": f})
    evidence["external_services"] = unique(evidence["external_services"])[:50]
    return evidence


def _manifest_dependency_names(archive, files, directory):
    names = set()
    for f in _direct_files(files, directory):
        b = basename(f)
        if b == "package.json":
            p = read_package_json(archive, f)
            for group in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                names.update(str(x).lower() for x in (p.get(group, {}) or {}).keys())
        elif b in {"requirements.txt", "pipfile"}:
            text = read_text_from_zip(archive, f, 500_000)
            for line in text.splitlines():
                m = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
                if m and not line.lstrip().startswith("#"):
                    names.add(m.group(1).lower())
    return names


def detect_dependencies(files, archive):
    """Detect infrastructure dependencies from service-local evidence, not repository-wide keywords."""
    service_dirs = {".": _direct_files(files, ".")}
    for path, _ in get_directories(files).items():
        direct = _direct_files(files, path)
        if direct and any(basename(f) in {"package.json", "requirements.txt", "pyproject.toml", "pom.xml", "go.mod", "cargo.toml", "gemfile", "composer.json"} for f in direct):
            service_dirs[path] = direct
    all_evidence = []
    for directory in service_dirs:
        ev = _service_local_dependency_evidence(archive, files, directory)
        if any(ev[k] for k in ("databases", "queues", "caches", "object_storage")):
            all_evidence.append((directory, ev))
    dependencies = {"databases": [], "queues": [], "caches": [], "object_storage": [], "external_services": []}
    evidence = {"databases": {}, "queues": {}, "caches": {}, "object_storage": {}, "external_services": []}
    for directory, ev in all_evidence:
        for category in ("databases", "queues", "caches", "object_storage"):
            for tech, hits in ev[category].items():
                if tech not in dependencies[category]:
                    dependencies[category].append(tech)
                evidence[category].setdefault(tech, []).append({"directory": directory, "evidence": hits})
    # External URLs are evidence, but service-host URLs are not infrastructure dependencies.
    hosts = set()
    for directory in service_dirs:
        ev = _service_local_dependency_evidence(archive, files, directory)
        for item in ev["external_services"]:
            hosts.add(item["host"])
            evidence["external_services"].append({"directory": directory, **item})
    # Do not report internal Compose/Kubernetes service hostnames as external services.
    internal_hosts = set()
    for d in service_dirs:
        internal_hosts.add(directory_name(d).lower() if d not in ("", ".") else "application")
    for f in files:
        b = basename(f)
        if b in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            txt = read_text_from_zip(archive, f, 1_000_000)
            for m in re.finditer(r"(?m)^\s{2}([A-Za-z0-9_.-]+):\s*$", txt): internal_hosts.add(m.group(1).lower())
    dependencies["external_services"] = sorted(h for h in hosts if h.lower() not in internal_hosts)[:100]
    return dependencies, evidence


def _infer_service_name_from_dir(path):
    return directory_name(path) if path not in ("", ".") else "application"


def _docker_stem(path):
    n = basename(path)
    if n in {"dockerfile", "containerfile"}:
        return None
    for suffix in (".dockerfile", ".containerfile"):
        if n.endswith(suffix):
            return n[:-len(suffix)]
    return None


def _dockerfile_metadata(archive, files, path):
    if not path:
        return {}
    text = read_text_from_zip(archive, path, 800_000)
    meta = {"path": path, "ports": [], "start": None, "copy_sources": []}
    for m in re.finditer(r"(?im)^\s*EXPOSE\s+(\d{2,5})", text):
        try: meta["ports"].append(int(m.group(1)))
        except ValueError: pass
    for m in re.finditer(r"(?im)^\s*(?:CMD|ENTRYPOINT)\s+(.+)$", text):
        raw = m.group(1).strip()
        try:
            arr = json.loads(raw)
            if isinstance(arr, list) and arr:
                meta["start"] = " ".join(str(x) for x in arr)
            else:
                meta["start"] = raw
        except Exception:
            meta["start"] = raw
    for m in re.finditer(r"(?im)^\s*COPY\s+(?:--[^ ]+\s+)*([^ ]+)\s+", text):
        src = m.group(1).strip().strip("./")
        if src and not src.startswith("--"):
            meta["copy_sources"].append(src.rstrip("/"))
    meta["ports"] = unique(meta["ports"])
    meta["copy_sources"] = unique(meta["copy_sources"])
    return meta


def detect_services(files, archive, compose_services, k8s_workloads):
    """Create logical services by merging source directories with deployment declarations."""
    directories = get_directories(files)
    candidates = []
    for path, _descendants in directories.items():
        direct = _direct_files(files, path)
        if not direct:
            continue
        tech, manifest, manifest_file = _manifest_data(archive, direct)
        frameworks, scripts, package, _ = _frameworks_and_scripts(archive, direct)
        source_text = "\n".join(read_text_from_zip(archive, f, 250_000) for f in direct if f.lower().endswith(CODE_EXTENSIONS))
        service_type = _classify_dynamic(directory_name(path), tech, frameworks, scripts, source_text)
        if service_type:
            candidates.append({
                "name": directory_name(path), "technology": (tech + " / " + " + ".join(frameworks)) if frameworks else tech,
                "type": service_type, "directory": path, "frameworks": frameworks,
                "scripts": scripts, "manifest": manifest, "manifest_file": manifest_file,
                "declared_replicas": None, "replica_source": "unknown", "compose_name": None,
                "detected_dependencies": _service_local_dependency_evidence(archive, files, path)
            })
    # Root application only when there is a root manifest and no stronger child services.
    root = _direct_files(files, ".")
    if root:
        tech, manifest, manifest_file = _manifest_data(archive, root)
        if tech != "Unknown":
            frameworks, scripts, package, _ = _frameworks_and_scripts(archive, root)
            if not any(s.get("directory") == "." for s in candidates):
                text = "\n".join(read_text_from_zip(archive, f, 250_000) for f in root if f.lower().endswith(CODE_EXTENSIONS))
                candidates.append({
                    "name": "application", "technology": (tech + " / " + " + ".join(frameworks)) if frameworks else tech,
                    "type": _classify_dynamic("application", tech, frameworks, scripts, text) or "backend",
                    "directory": ".", "frameworks": frameworks, "scripts": scripts,
                    "manifest": manifest, "manifest_file": manifest_file,
                    "declared_replicas": None, "replica_source": "unknown", "compose_name": None,
                    "detected_dependencies": _service_local_dependency_evidence(archive, files, ".")
                })
    # Merge Compose declarations with source services by build context, then by exact name.
    used = set()
    logical = []
    for item in compose_services:
        build_dir = _compose_build_dir(item)
        match = None
        if build_dir:
            for c in candidates:
                if clean_path(c["directory"]) == build_dir or clean_path(c["directory"]).rstrip("/") == build_dir.rstrip("/"):
                    match = c; break
        # When Compose uses context: . with a named Dockerfile, match the Dockerfile stem
        # or its COPY source to the actual application directory.
        if match is None and item.get("dockerfile"):
            df = clean_path(item["dockerfile"])
            stem = _docker_stem(df)
            for c in candidates:
                if stem and c["name"].lower() == stem.lower():
                    match = c; break
                meta = _dockerfile_metadata(archive, files, df)
                if c["directory"] in meta.get("copy_sources", []):
                    match = c; break
        if match is None:
            for c in candidates:
                if c["name"].lower() == item["name"].lower():
                    match = c; break
        if match is not None:
            match = dict(match)
            match["name"] = item["name"]
            match["compose_name"] = item["name"]
            if item.get("replicas") is not None:
                match["declared_replicas"] = item["replicas"]
                match["replica_source"] = "docker-compose"
            match["compose"] = item
            match["dockerfile"] = item.get("dockerfile")
            match["docker"] = _dockerfile_metadata(archive, files, item.get("dockerfile"))
            logical.append(match)
            used.add(id(next(c for c in candidates if c is not None and c.get("directory") == match.get("directory")))) if False else None
        else:
            image = item.get("image")
            tech = "Container"
            if image:
                low = image.lower()
                if "node" in low: tech = "Node.js"
                elif "python" in low: tech = "Python"
                elif "nginx" in low: tech = "Nginx"
            docker_meta = _dockerfile_metadata(archive, files, item.get("dockerfile"))
            inferred_dir = next((x for x in docker_meta.get("copy_sources", []) if x in {c["name"] for c in candidates}), build_dir or "")
            logical.append({
                "name": item["name"], "technology": tech, "type": _compose_service_type(item),
                "directory": inferred_dir, "frameworks": [], "scripts": {}, "manifest": {},
                "manifest_file": None, "declared_replicas": item.get("replicas"),
                "replica_source": "docker-compose" if item.get("replicas") is not None else "unknown",
                "compose_name": item["name"], "compose": item, "dockerfile": item.get("dockerfile"), "docker": docker_meta,
                "detected_dependencies": _service_local_dependency_evidence(archive, files, inferred_dir) if inferred_dir else {"databases": {}, "queues": {}, "caches": {}, "object_storage": {}, "external_services": []}
            })
    # Add source candidates not represented by Compose.
    compose_dirs = {clean_path(_compose_build_dir(x)).rstrip("/") for x in compose_services if _compose_build_dir(x)}
    compose_names = {x["name"].lower() for x in compose_services}
    represented_dirs = set(compose_dirs)
    represented_names = set(compose_names)
    for item in compose_services:
        if item.get("dockerfile"):
            df = clean_path(item["dockerfile"])
            stem = _docker_stem(df)
            if stem:
                represented_names.add(stem.lower())
            meta = _dockerfile_metadata(archive, files, df)
            for src in meta.get("copy_sources", []):
                represented_names.add(directory_name(src).lower())
    for c in candidates:
        if clean_path(c["directory"]).rstrip("/") in represented_dirs or c["name"].lower() in represented_names:
            continue
        logical.append(c)
    # Add Kubernetes workloads not represented by an existing logical service.
    for k in k8s_workloads:
        if any(s["name"].lower() == k["name"].lower() for s in logical):
            continue
        logical.append({
            "name": k["name"], "technology": "Kubernetes", "type": _classify_dynamic(k["name"], "Kubernetes", [], {}, "") or "backend",
            "directory": "", "frameworks": [], "scripts": {}, "manifest": {}, "manifest_file": None,
            "declared_replicas": k.get("replicas"), "replica_source": "kubernetes", "compose_name": None,
            "kubernetes": k, "detected_dependencies": {"databases": {}, "queues": {}, "caches": {}, "object_storage": {}, "external_services": []}
        })
    # Attach container-only Dockerfiles only when no logical service already represents the stem.
    for dockerfile in _docker_named_files(files):
        stem = _docker_stem(dockerfile)
        if not stem:
            continue
        if any(s["name"].lower() == stem.lower() or directory_name(s.get("directory", "")).lower() == stem.lower() for s in logical if s.get("directory") or s.get("name")):
            continue
        logical.append({
            "name": stem, "technology": "Container", "type": _classify_dynamic(stem, "Container", [], {}, "", image="container") or "backend",
            "directory": "", "frameworks": [], "scripts": {}, "manifest": {}, "manifest_file": None,
            "declared_replicas": None, "replica_source": "unknown", "compose_name": None,
            "dockerfile": dockerfile, "detected_dependencies": {"databases": {}, "queues": {}, "caches": {}, "object_storage": {}, "external_services": []}
        })
    # Stable unique logical identities.
    result = []
    seen = set()
    for s in logical:
        key = (s["name"].lower(), clean_path(s.get("directory", "")), s["type"])
        if key not in seen:
            seen.add(key); result.append(s)
    return result


def detect_service_health(services, files, archive):
    result = {}
    for service in services:
        directory = service.get("directory", "")
        candidates = _all_files_under(files, directory) if directory else []
        for f in candidates:
            if not f.lower().endswith(CODE_EXTENSIONS):
                continue
            content = read_text_from_zip(archive, f, 500_000)
            matches = HEALTH_ROUTE_PATTERN.findall(content)
            if matches:
                result[service["name"]] = sorted(unique(matches), key=len)[0]
                break
    return result


def _service_aliases(service):
    aliases = {service["name"].lower()}
    if service.get("compose_name"):
        aliases.add(service["compose_name"].lower())
    d = clean_path(service.get("directory", ""))
    if d and d != ".":
        aliases.add(directory_name(d).lower())
    return aliases


def _find_target_service(host, services):
    h = (host or "").lower().strip().rstrip(".")
    if not h:
        return None
    for s in services:
        if h in _service_aliases(s):
            return s
    # common URL forms can include service:port; host is already normalized by urlparse.
    return None


def detect_service_urls(services, files, archive):
    refs = []
    for source in services:
        # Compose environment variables are first-class evidence.
        compose = source.get("compose") or {}
        for key, value in (compose.get("environment_values") or {}).items():
            if not isinstance(value, str) or "://" not in value:
                continue
            try:
                target = _find_target_service(urlparse(value).hostname, services)
            except Exception:
                target = None
            if target and target["name"] != source["name"]:
                refs.append({"from": source["name"], "to": target["name"], "file": compose.get("file", "docker-compose.yml"), "relationship": "request", "evidence": f"{key}={value}", "confidence": "high"})
        directory = source.get("directory", "")
        relevant = _all_files_under(files, directory) if directory else []
        for f in relevant[:500]:
            if is_ignored(f) or not f.lower().endswith(SOURCE_EXTENSIONS):
                continue
            content = read_text_from_zip(archive, f, 500_000)
            # URLs and URI-like environment values. Only create service edges when the host matches a discovered service.
            urls = re.findall(r"(?:https?|redis|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|amqp)://[^\s'\"`<>]+", content, flags=re.I)
            for raw in urls:
                try:
                    parsed = urlparse(raw)
                    target = _find_target_service(parsed.hostname, services)
                except Exception:
                    target = None
                if target and target["name"] != source["name"]:
                    refs.append({"from": source["name"], "to": target["name"], "file": f, "relationship": "request", "evidence": raw[:180], "confidence": "high"})
            # Also inspect explicit service URL environment variables whose values are URLs.
            for m in re.finditer(r"\b([A-Z][A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT)[A-Z0-9_]*)\s*[:=]\s*['\"]?([^\s'\"\n]+)", content):
                value = m.group(2)
                try:
                    target = _find_target_service(urlparse(value).hostname, services)
                except Exception:
                    target = None
                if target and target["name"] != source["name"]:
                    refs.append({"from": source["name"], "to": target["name"], "file": f, "relationship": "request", "evidence": m.group(0)[:180], "confidence": "high"})
    return unique(refs)


def build_architecture(services, dependencies, compose_services, k8s_workloads):
    nodes = []
    connections = []
    for s in services:
        node = {"name": s["name"], "type": s["type"], "technology": s["technology"]}
        if s.get("declared_replicas") is not None:
            node["replicas"] = s["declared_replicas"]
            node["replica_source"] = s.get("replica_source", "declared")
        else:
            node["replicas"] = None
            node["replica_source"] = "unknown"
        nodes.append(node)
    for category, ntype in (("databases", "database"), ("queues", "queue"), ("caches", "cache"), ("object_storage", "object_storage")):
        for dep in dependencies[category]:
            nodes.append({"name": dep.lower().replace(" ", "-"), "type": ntype, "technology": dep})
    # Compose relationships are explicit evidence.
    service_by_name = {s["name"].lower(): s for s in services}
    aliases = {}
    for s in services:
        for a in _service_aliases(s): aliases[a] = s
    for s in services:
        compose = s.get("compose") or {}
        for dep in compose.get("depends_on", []):
            target = aliases.get(dep.lower())
            if target and target["name"] != s["name"]:
                connections.append({"from": s["name"], "to": target["name"], "relationship": "depends_on", "inference": "Docker Compose", "confidence": "high", "evidence": "depends_on"})
    # Source-code URL references are strongest dynamic evidence.
    for s in services:
        directory = s.get("directory", "")
        for f in (_all_files_under(_ANALYSIS_FILES, directory) if directory else []):
            pass
    # Service-local dependencies.
    for s in services:
        ev = s.get("detected_dependencies") or {}
        for category, ntype in (("databases", "database"), ("queues", "queue"), ("caches", "cache"), ("object_storage", "object_storage")):
            for dep in ev.get(category, {}):
                node_name = dep.lower().replace(" ", "-")
                connections.append({"from": s["name"], "to": node_name, "relationship": ntype, "inference": "service-local dependency evidence", "confidence": "medium", "evidence": ev[category][dep][:3]})
    # detect_service_urls is called separately by the endpoint; store refs globally for this invocation.
    for ref in globals().get("_CURRENT_SERVICE_URL_REFS", []):
        connections.append(ref)
    return {"nodes": unique(nodes), "connections": unique(connections)}


def analyze_reliability(services, dependencies, health_endpoints, service_health, dockerfiles, zerops_configs, compose_services, k8s_workloads, env_info, ci_cd, iac):
    findings = []
    for s in services:
        replicas = s.get("declared_replicas")
        if replicas is not None and replicas < 2 and s["type"] in {"backend", "frontend", "worker"}:
            severity = "critical" if s["type"] == "backend" else "warning"
            impact = 18 if severity == "critical" else 7
            findings.append(make_finding(severity, "availability", f"{s['name']} Redundancy Not Detected",
                f"The deployment configuration explicitly declares {replicas} instance(s) for {s['name']}.",
                f"Consider running at least 2 {s['name']} instances where the workload and platform support horizontal redundancy.", impact))
        elif replicas is None and s["type"] in {"backend", "frontend", "worker"}:
            findings.append(make_finding("info", "availability", f"{s['name']} Replica Count Unknown",
                f"No explicit replica count was found for {s['name']} in the analyzed deployment configuration.",
                "Verify the production service's scaling and redundancy policy rather than assuming a replica count from source code.", 0))
    app_services = [s for s in services if s["type"] in {"backend", "worker"}]
    if not health_endpoints:
        findings.append(make_finding("warning", "observability", "Health Check Not Detected",
            "No common application health endpoint was detected.", "Expose a service-specific readiness/health endpoint where appropriate.", 8))
    else:
        missing = [s["name"] for s in app_services if s["name"] not in service_health]
        if missing:
            findings.append(make_finding("warning", "observability", "Some Services Lack Health Checks",
                "Health endpoints exist, but some application services do not have a service-specific endpoint detected.",
                "Add service-specific health/readiness checks where appropriate.", 4))
    for db in dependencies["databases"]:
        findings.append(make_finding("warning", "data", f"{db} Availability Must Be Reviewed",
            f"{db} was detected from service-local dependency evidence. Static analysis cannot confirm its production availability model.",
            f"Review {db} replication, backups, failover, connection pooling and recovery requirements.", 5))
    if any(s["type"] == "worker" for s in services) and not dependencies["queues"]:
        findings.append(make_finding("info", "async", "Worker Queue Not Detected",
            "Worker-like application code was detected but no queue technology was identified from service-local evidence.",
            "If these workers consume asynchronous jobs, verify the queue or broker configuration.", 2))
    if not dockerfiles and not compose_services and not k8s_workloads:
        findings.append(make_finding("info", "deployment", "Container / Orchestration Configuration Not Detected",
            "No Dockerfile, Compose service definition or Kubernetes workload was detected.",
            "Add explicit deployment configuration if reproducible containerized deployment is required.", 2))
    if zerops_configs:
        findings.append(make_finding("info", "deployment", "Existing Zerops Configuration Detected",
            "A Zerops deployment configuration exists in the project.",
            "Compare it with the generated configuration and keep project-specific deployment decisions under version control.", 0))
    exposed = [x for x in env_info.get("potential_secrets", []) if x.get("value_exposed")]
    if exposed:
        findings.append(make_finding("critical", "security", "Potential Secrets Found in Environment Files",
            f"{len(exposed)} secret-like environment variables appear to contain values in uploaded files.",
            "Do not commit real credentials. Rotate exposed secrets and use deployment secret management.", 20))
    if not ci_cd:
        findings.append(make_finding("info", "delivery", "CI/CD Configuration Not Detected",
            "No common CI/CD workflow was detected.", "Add automated build, test and deployment checks before production rollout.", 2))
    if not iac:
        findings.append(make_finding("info", "infrastructure", "Infrastructure-as-Code Not Detected",
            "No Terraform/Pulumi-style infrastructure configuration was detected.", "Consider versioning infrastructure configuration when infrastructure complexity grows.", 1))
    if not services:
        findings.append(make_finding("critical", "analysis", "Application Service Could Not Be Identified",
            "The analyzer could not confidently identify an application service.", "Provide a supported manifest or deployment configuration, or keep an identifiable application entrypoint.", 25))
    return findings


def detect_bottlenecks(services, dependencies, findings, architecture):
    candidates = []
    inbound = {s["name"]: 0 for s in services}
    outbound = {s["name"]: 0 for s in services}
    for c in architecture.get("connections", []):
        if c.get("from") in outbound: outbound[c["from"]] += 1
        if c.get("to") in inbound: inbound[c["to"]] += 1
    for s in services:
        score = inbound.get(s["name"], 0) * 20 + outbound.get(s["name"], 0) * 5
        if s.get("declared_replicas") == 1:
            score += 35
        if score >= 25:
            candidates.append({"component": s["name"], "type": "service", "risk": "medium" if score < 60 else "high",
                "reason": f"Detected dependency graph shows {inbound.get(s['name'],0)} inbound and {outbound.get(s['name'],0)} outbound relationship(s).",
                "priority": min(100, score)})
    for db in dependencies["databases"]:
        candidates.append({"component": db, "type": "database", "risk": "medium",
            "reason": "A service-local database dependency was detected; static analysis cannot determine its capacity or HA configuration.", "priority": 50})
    for q in dependencies["queues"]:
        candidates.append({"component": q, "type": "queue", "risk": "medium",
            "reason": "A service-local messaging dependency was detected; queue capacity and backlog behavior are runtime concerns.", "priority": 45})
    candidates.sort(key=lambda x: x["priority"], reverse=True)
    return candidates[:10]


def build_optimization_plan(services, dependencies, findings, deployment):
    actions = []
    for s in services:
        replicas = s.get("declared_replicas")
        if replicas == 1 and s["type"] in {"backend", "frontend", "worker"}:
            actions.append({"priority": "high" if s["type"] == "backend" else "medium", "service": s["name"], "action": "Increase redundancy", "current": "1 declared instance", "recommended": "2+ instances where supported", "why": "The deployment explicitly declares one instance."})
        elif replicas is None and s["type"] in {"backend", "frontend", "worker"}:
            actions.append({"priority": "info", "service": s["name"], "action": "Verify scaling policy", "current": "Replica count not declared", "recommended": "Set production scaling explicitly", "why": "Static source analysis cannot assume the runtime replica count."})
        if s["name"] not in deployment.get("health_endpoints_by_service", {}) and s["type"] in {"backend", "worker"}:
            actions.append({"priority": "medium", "service": s["name"], "action": "Add service health check", "current": "Not detected", "recommended": "/health or another service-specific endpoint", "why": "Health checks allow unhealthy instances to be removed from service."})
    if not actions:
        actions.append({"priority": "info", "service": "application", "action": "No static optimization required", "current": "No high-confidence configuration gap detected", "recommended": "Validate runtime capacity and failure behavior", "why": "Static analysis cannot replace production load and failure testing."})
    return {"actions": actions, "current_reliability": None, "optimized_reliability": None, "improvement": None}


def _yaml_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'


def _node_start(service):
    scripts = service.get("scripts") or {}
    if "start" in scripts: return "npm start"
    if "start:prod" in scripts: return "npm run start:prod"
    if "serve" in scripts: return "npm run serve"
    docker = service.get("docker") or {}
    if docker.get("start"): return docker["start"]
    return None


def _python_entry(service):
    files = []
    mf = service.get("manifest_file")
    if mf: files.append(mf)
    d = service.get("directory", "")
    # Prefer common executable names only as an evidence-based fallback.
    candidates = ["app.py", "main.py", "server.py", "run.py"]
    for name in candidates:
        files.append(clean_path(d + "/" + name) if d and d != "." else name)
    for f in files:
        if f.lower().endswith(".py"):
            return f
    return "main.py"


def generate_zerops_config(services, service_health):
    """Generate a conservative, evidence-derived zerops.yaml using the current Zerops schema."""
    lines = ["# Generated by Zerops Autopilot", "# Review all commands, service names and ports before deployment.", "", "zerops:"]
    for s in services:
        name = re.sub(r"[^A-Za-z0-9_-]", "-", s["name"]).strip("-") or "app"
        tech = (s.get("technology") or "").lower()
        directory = clean_path(s.get("directory", ""))
        indent = "  "
        lines.append(f"{indent}- setup: {name}")
        # Only add build when there is evidence that a build is needed.
        if "node.js" in tech or "node" in tech:
            if directory and directory != ".":
                lines += [f"    build:", f"      base: nodejs@latest", f"      buildCommands:", f"        - cd {directory} && npm install"]
                if "build" in (s.get("scripts") or {}):
                    lines.append(f"        - cd {directory} && npm run build")
                if "frontend" == s["type"] and ("vite" in tech or "dist" in directory.lower() or "react" in tech):
                    lines += [f"      deployFiles:", f"        - ./{directory}/dist"]
                else:
                    lines += [f"      deployFiles:", f"        - ./{directory}/~"]
            else:
                lines += [f"    build:", f"      base: nodejs@latest", f"      buildCommands:", f"        - npm install"]
                if "build" in (s.get("scripts") or {}): lines.append("        - npm run build")
                lines += [f"      deployFiles:", f"        - ./~"]
            lines += [f"    run:", f"      base: nodejs@latest"]
            start = _node_start(s)
            if start:
                lines.append(f"      start: {start if not directory or directory == '.' else 'cd ' + directory + ' && ' + start}")
            else:
                lines.append("      # start command could not be determined with high confidence")
        elif "python" in tech:
            if directory and directory != ".":
                lines += [f"    build:", f"      base: python@latest", f"      deployFiles:", f"        - ./{directory}/~"]
                lines += [f"    run:", f"      base: python@latest", f"      prepareCommands:", f"        - python3 -m pip install -r {directory}/requirements.txt --ignore-installed"]
                lines.append(f"      start: python3 {_python_entry(s)}")
            else:
                lines += [f"    build:", f"      base: python@latest", f"      deployFiles:", f"        - ./~", f"    run:", f"      base: python@latest", f"      prepareCommands:", f"        - python3 -m pip install -r requirements.txt --ignore-installed", f"      start: python3 {_python_entry(s)}"]
        else:
            lines += [f"    run:", f"      base: nodejs@latest", f"      # Runtime command was not inferred with high confidence."]
        # Port evidence from Compose is safest; otherwise omit ports rather than inventing 3000.
        compose = s.get("compose") or {}
        ports = compose.get("ports") or []
        if ports:
            # Insert ports before start is cumbersome; rebuild run block is unnecessary for UI output.
            # We append valid run keys after start; YAML order is irrelevant.
            lines += ["      ports:"]
            for p in ports:
                lines += [f"        - port: {p}", "          httpSupport: true"]
        health = service_health.get(s["name"])
        if health and ports:
            lines += ["      healthCheck:", "        httpGet:", f"          port: {ports[0]}", f"          path: {health}"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def calculate_score(findings):
    score = 100
    for item in findings:
        score -= int(item.get("score_impact", 0) or 0)
    return max(0, min(100, score))


def home():

    return jsonify({

        "service":
            "Zerops Autopilot Analyzer",

        "status":
            "running",

        "version":
            VERSION,

        "mode":
            "static-analysis",

        "ai_required":
            False,

        "database_required":
            False

    })


def health():

    return jsonify({

        "status":
            "healthy",

        "service":
            "zerops-autopilot-analyzer",

        "version":
            VERSION

    })


def analyze_project():

    if "project" not in request.files:

        return jsonify({

            "error":
                "No project file received"

        }), 400

    project = request.files[
        "project"
    ]

    if not project.filename:

        return jsonify({

            "error":
                "Uploaded project has no filename"

        }), 400

    with tempfile.TemporaryDirectory() as temp_dir:

        zip_path = os.path.join(
            temp_dir,
            "project.zip"
        )

        project.save(
            zip_path
        )

        if not zipfile.is_zipfile(
            zip_path
        ):

            return jsonify({

                "error":
                    "Uploaded file is not a valid ZIP archive"

            }), 400

        try:

            with zipfile.ZipFile(
                zip_path,
                "r"
            ) as archive:

                files = [

                    clean_path(name)

                    for name
                    in archive.namelist()

                    if not name.endswith("/")

                    and clean_path(name)

                    and not is_ignored(name)

                ]

                technologies = detect_technologies(
                    files,
                    archive
                )

                compose_files = detect_compose_files(
                    files
                )

                compose_services = parse_compose_services(
                    archive,
                    compose_files
                )

                kubernetes_files = detect_kubernetes_files(
                    files,
                    archive
                )

                k8s_workloads = parse_kubernetes_workloads(
                    kubernetes_files,
                    archive
                )

                services = detect_services(
                    files,
                    archive,
                    compose_services,
                    k8s_workloads
                )

                dependencies, dependency_evidence = (
                    detect_dependencies(
                        files,
                        archive
                    )
                )

                ports = detect_ports(
                    files,
                    archive
                )

                health_endpoints = (
                    detect_health_endpoints(
                        files,
                        archive
                    )
                )

                service_health = detect_service_health(
                    services,
                    files,
                    archive
                )

                dockerfiles = detect_docker(
                    files
                )

                zerops_configs = detect_zerops(
                    files
                )

                ci_cd = detect_ci_cd(
                    files
                )

                iac = detect_iac(
                    files
                )

                env_info = detect_environment(
                    files,
                    archive
                )

                service_url_references = (
                    detect_service_urls(
                        services,
                        files,
                        archive
                    )
                )

                global _ANALYSIS_FILES, _CURRENT_SERVICE_URL_REFS
                _ANALYSIS_FILES = files
                _CURRENT_SERVICE_URL_REFS = service_url_references

                architecture = build_architecture(
                    services,
                    dependencies,
                    compose_services,
                    k8s_workloads
                )

                findings = analyze_reliability(
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
                    iac
                )

                reliability_score = (
                    calculate_score(
                        findings
                    )
                )

                risk_summary = (
                    calculate_risk_summary(
                        findings
                    )
                )

                bottlenecks = (
                    detect_bottlenecks(
                        services,
                        dependencies,
                        findings,
                        architecture
                    )
                )

                deployment = {

                    "ports":
                        ports,

                    "health_endpoints":
                        health_endpoints,

                    "health_endpoints_by_service":
                        service_health,

                    "service_health":
                        service_health,

                    "dockerfiles":
                        dockerfiles,

                    "zerops_configs":
                        zerops_configs,

                    "compose_files":
                        compose_files,

                    "kubernetes_files":
                        kubernetes_files,

                    "ci_cd":
                        ci_cd,

                    "iac":
                        iac,

                    "environment_files":
                        env_info["files"]

                }

                optimization_plan = (
                    build_optimization_plan(
                        services,
                        dependencies,
                        findings,
                        deployment
                    )
                )

                zerops_yml = (
                    generate_zerops_config(
                        services,
                        service_health
                    )
                )

                failure_scenarios = (
                    build_failure_scenarios(
                        services,
                        dependencies
                    )
                )

                summary = build_summary(
                    services,
                    technologies,
                    dependencies,
                    reliability_score,
                    risk_summary,
                    bottlenecks
                )

                response = {

                    "status":
                        "success",

                    "analyzer": {

                        "name":
                            "Zerops Autopilot Analyzer",

                        "version":
                            VERSION,

                        "mode":
                            "static-analysis",

                        "ai_required":
                            False,

                        "database_required":
                            False

                    },

                    "project":
                        project.filename,

                    "file_count":
                        len(files),

                    "summary":
                        summary,

                    "technologies":
                        technologies,

                    "services":
                        services,

                    "dependencies":
                        dependencies,

                    "dependency_evidence":
                        dependency_evidence,

                    "deployment":
                        deployment,

                    "environment": {

                        "files":
                            env_info["files"],

                        "variable_count":
                            len(
                                env_info["variables"]
                            ),

                        "variables":
                            env_info["variables"][:200],

                        "potential_secrets":
                            env_info["potential_secrets"]

                    },

                    "service_url_references":
                        service_url_references,

                    "compose_services":
                        compose_services,

                    "kubernetes_workloads":
                        k8s_workloads,

                    "architecture":
                        architecture,

                    "failure_scenarios":
                        failure_scenarios,

                    "reliability_score":
                        reliability_score,

                    "risk_summary":
                        risk_summary,

                    "findings":
                        findings,

                    "bottlenecks":
                        bottlenecks,

                    "optimization_plan":
                        optimization_plan,

                    "zeropsYml":
                        zerops_yml,

                    "files":
                        files[:200]

                }

        except zipfile.BadZipFile:

            return jsonify({

                "error":
                    "The uploaded ZIP file is corrupted"

            }), 400

        except Exception as error:

            app.logger.exception(
                "Project analysis failed"
            )

            return jsonify({

                "error":
                    "Project analysis failed",

                "details":
                    str(error)

            }), 500

    print(
        "\n======================================"
    )

    print(
        "ZEROPS AUTOPILOT ANALYSIS"
    )

    print(
        "======================================"
    )

    print(
        "Project:",
        project.filename
    )

    print(
        "Files:",
        len(files)
    )

    print(
        "Technologies:",
        technologies
    )

    print(
        "Services:",
        [
            f"{service['name']} "
            f"({service['type']})"
            for service in services
        ]
    )

    print(
        "Databases:",
        dependencies["databases"]
    )

    print(
        "Queues:",
        dependencies["queues"]
    )

    print(
        "Caches:",
        dependencies["caches"]
    )

    print(
        "Health:",
        health_endpoints
    )

    print(
        "Reliability:",
        reliability_score
    )

    print(
        "Risk:",
        risk_summary["level"]
    )

    print(
        "Top bottleneck:",
        (
            bottlenecks[0]["component"]
            if bottlenecks
            else "None"
        )
    )

    print(
        "======================================\n"
    )

    return jsonify(
        response
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )