const express = require("express");
const cors = require("cors");
const multer = require("multer");
const fs = require("fs");
const path = require("path");
const FormData = require("form-data");
const axios = require("axios");

const app = express();

// =====================================================
// CONFIGURATION
// =====================================================

const PORT = Number(process.env.PORT || 3000);
const ANALYZER_URL =
  process.env.ANALYZER_URL || "http://analyzer:5000";

const UPLOAD_DIR =
  process.env.UPLOAD_DIR ||
  path.join(__dirname, "uploads");

const MAX_FILE_SIZE = 100 * 1024 * 1024;
const ANALYZER_TIMEOUT = 120000;

if (!fs.existsSync(UPLOAD_DIR)) {
  fs.mkdirSync(UPLOAD_DIR, {
    recursive: true
  });
}

// =====================================================
// MIDDLEWARE
// =====================================================

app.use(cors());

app.use(
  express.json({
    limit: "10mb"
  })
);

app.use(
  express.urlencoded({
    extended: true
  })
);

const upload = multer({
  dest: UPLOAD_DIR,

  limits: {
    fileSize: MAX_FILE_SIZE
  },

  fileFilter: (req, file, cb) => {

    if (
      path
        .extname(file.originalname)
        .toLowerCase() === ".zip"
    ) {
      return cb(null, true);
    }

    cb(
      new Error(
        "Only ZIP project archives are supported."
      )
    );
  }
});

// =====================================================
// SAFE HELPERS
// =====================================================

function safeArray(value) {
  return Array.isArray(value)
    ? value
    : [];
}

function safeObject(value) {
  return (
    value &&
    typeof value === "object" &&
    !Array.isArray(value)
  )
    ? value
    : {};
}

function getServices(analysis) {
  return safeArray(
    analysis?.services
  );
}

function getFindings(analysis) {
  return safeArray(
    analysis?.findings
  );
}

function getDependencies(analysis) {
  return safeObject(
    analysis?.dependencies
  );
}

function getDeployment(analysis) {
  return safeObject(
    analysis?.deployment
  );
}

function serviceNames(services) {
  return services
    .map(
      service => service?.name
    )
    .filter(Boolean);
}

function serviceByName(
  services,
  name
) {
  return services.find(
    service =>
      String(service?.name) ===
      String(name)
  );
}

function normalizeTechnology(service) {

  const technology =
    String(
      service?.technology || ""
    ).toLowerCase();

  if (
    technology.includes("python")
  ) {
    return "python";
  }

  if (
    technology.includes("java")
  ) {
    return "java";
  }

  if (
    technology.includes("go")
  ) {
    return "go";
  }

  if (
    technology.includes("rust")
  ) {
    return "rust";
  }

  if (
    technology.includes("php")
  ) {
    return "php";
  }

  if (
    technology.includes("ruby")
  ) {
    return "ruby";
  }

  if (
    technology.includes("node") ||
    technology.includes("javascript") ||
    technology.includes("typescript")
  ) {
    return "nodejs";
  }

  if (
    technology.includes("docker") ||
    technology.includes("container")
  ) {
    return "docker";
  }

  return "nodejs";
}

function getPort(service) {

  if (
    service?.port !== undefined &&
    service?.port !== null
  ) {
    return service.port;
  }

  if (
    Array.isArray(service?.ports) &&
    service.ports.length
  ) {

    const first =
      service.ports[0];

    return typeof first === "object"
      ? (
          first.container ||
          first.port ||
          first.target
        )
      : first;
  }

  return null;
}

function getStartCommand(service) {

  return (
    service?.startCommand ||
    service?.start_command ||
    service?.command ||
    service?.runCommand ||
    null
  );
}

function getHealthPath(
  service,
  deployment
) {

  const serviceHealth =
    safeObject(
      deployment?.service_health ||
      deployment?.health_endpoints_by_service
    );

  if (
    serviceHealth[
      service?.name
    ]
  ) {
    return serviceHealth[
      service.name
    ];
  }

  if (
    typeof service?.healthCheck ===
    "string"
  ) {
    return service.healthCheck;
  }

  if (
    service?.healthCheck?.path
  ) {
    return service.healthCheck.path;
  }

  return (
    service?.health_endpoint ||
    service?.healthEndpoint ||
    null
  );
}

function yamlQuote(value) {
  return JSON.stringify(
    String(value)
  );
}

function unique(values) {
  return [
    ...new Set(
      values.filter(Boolean)
    )
  ];
}

// =====================================================
// RELIABILITY / READINESS
// =====================================================

function calculateReliability(
  analysis
) {

  const findings =
    getFindings(analysis);

  let score =
    Number.isFinite(
      Number(
        analysis?.reliability_score
      )
    )
      ? Number(
          analysis.reliability_score
        )
      : 100;

  if (
    !Number.isFinite(
      Number(
        analysis?.reliability_score
      )
    )
  ) {

    findings.forEach(
      finding => {

        const severity =
          String(
            finding?.severity || ""
          ).toLowerCase();

        if (
          severity === "critical"
        ) {
          score -= 30;
        } else if (
          severity === "warning"
        ) {
          score -= 10;
        } else if (
          severity === "info"
        ) {
          score -= 2;
        }

      }
    );
  }

  return Math.max(
    0,
    Math.min(
      100,
      Math.round(score)
    )
  );
}

function calculateReadiness(
  analysis
) {

  const services =
    getServices(analysis);

  const findings =
    getFindings(analysis);

  const deployment =
    getDeployment(analysis);

  const dependencies =
    getDependencies(analysis);

  const critical =
    findings.filter(
      finding =>
        finding?.severity ===
        "critical"
    ).length;

  const warnings =
    findings.filter(
      finding =>
        finding?.severity ===
        "warning"
    ).length;

  const health =
    safeObject(
      deployment.service_health ||
      deployment.health_endpoints_by_service
    );

  const hasHealthChecks =
    Object.keys(health).length > 0 ||
    safeArray(
      deployment.health_endpoints
    ).length > 0;

  const hasContainers =
    safeArray(
      deployment.dockerfiles
    ).length > 0 ||
    safeArray(
      deployment.compose_files
    ).length > 0 ||
    safeArray(
      deployment.kubernetes_files
    ).length > 0;

  const hasCI =
    safeArray(
      deployment.ci_cd ||
      deployment.cicd
    ).length > 0;

  const hasIaC =
    safeArray(
      deployment.infrastructure_as_code ||
      deployment.iac
    ).length > 0;

  const databases =
    safeArray(
      dependencies.databases
    );

  const queues =
    safeArray(
      dependencies.queues
    );

  const caches =
    safeArray(
      dependencies.caches
    );

  let architecture =
    services.length
      ? 100
      : 30;

  architecture -=
    critical * 15 +
    warnings * 5;

  architecture =
    Math.max(
      0,
      Math.min(
        100,
        architecture
      )
    );

  let deploymentScore = 30;

  if (hasContainers) {
    deploymentScore += 20;
  }

  if (hasHealthChecks) {
    deploymentScore += 20;
  }

  if (hasCI) {
    deploymentScore += 15;
  }

  if (hasIaC) {
    deploymentScore += 15;
  }

  deploymentScore =
    Math.min(
      100,
      deploymentScore
    );

  let resilience = 50;

  const backends =
    services.filter(
      service =>
        service.type ===
        "backend"
    ).length;

  const workers =
    services.filter(
      service =>
        service.type ===
        "worker"
    ).length;

  if (backends > 1) {
    resilience += 15;
  }

  if (workers > 1) {
    resilience += 10;
  }

  if (queues.length) {
    resilience += 10;
  }

  if (databases.length) {
    resilience += 5;
  }

  if (caches.length) {
    resilience += 5;
  }

  resilience =
    Math.min(
      100,
      resilience
    );

  const overall =
    Math.round(
      (
        architecture +
        deploymentScore +
        resilience
      ) / 3
    );

  return {

    overall,

    architecture,

    deployment:
      deploymentScore,

    resilience,

    productionReady:
      overall >= 80 &&
      critical === 0,

    criticalIssues:
      critical,

    warnings,

    services:
      services.length,

    databases:
      databases.length,

    queues:
      queues.length,

    caches:
      caches.length,

    ciCdDetected:
      hasCI,

    infrastructureAsCodeDetected:
      hasIaC

  };
}

// =====================================================
// DEPENDENCY / ARCHITECTURE GRAPH
// =====================================================

function buildDependencyGraph(
  analysis
) {

  const services =
    getServices(analysis);

  const dependencies =
    getDependencies(analysis);

  const nodes =
    services.map(
      service => ({

        id:
          service.name,

        name:
          service.name,

        type:
          service.type,

        technology:
          service.technology

      })
    );

  const edges = [];

  const addEdge = (
    source,
    target,
    type = "depends_on"
  ) => {

    if (
      source &&
      target &&
      source !== target
    ) {

      edges.push({
        source,
        target,
        type
      });

    }
  };

  services.forEach(
    service => {

      safeArray(
        service.dependencies
      ).forEach(
        dependency =>
          addEdge(
            service.name,
            typeof dependency ===
            "string"
              ? dependency
              : dependency?.name
          )
      );

      safeArray(
        service.depends_on
      ).forEach(
        dependency =>
          addEdge(
            service.name,
            typeof dependency ===
            "string"
              ? dependency
              : dependency?.name
          )
      );

    }
  );

  safeArray(
    dependencies.services
  ).forEach(
    dependency => {

      if (
        !dependency ||
        typeof dependency !==
          "object"
      ) {
        return;
      }

      addEdge(
        dependency.source ||
          dependency.from ||
          dependency.service,

        dependency.target ||
          dependency.to ||
          dependency.depends_on,

        dependency.type ||
          "depends_on"
      );

    }
  );

  safeArray(
    analysis?.architecture
      ?.connections
  ).forEach(
    connection => {

      addEdge(
        connection.from ||
          connection.source,

        connection.to ||
          connection.target,

        connection.relationship ||
          connection.type ||
          "depends_on"
      );

    }
  );

  const uniqueEdges = [];
  const seen = new Set();

  edges.forEach(
    edge => {

      const key =
        `${edge.source}::${edge.target}::${edge.type}`;

      if (
        !seen.has(key)
      ) {

        seen.add(key);

        uniqueEdges.push(
          edge
        );

      }

    }
  );

  const knownNodeIds =
    new Set(
      nodes.map(
        node => node.id
      )
    );

  uniqueEdges.forEach(
    edge => {

      if (
        !knownNodeIds.has(
          edge.target
        )
      ) {

        nodes.push({

          id:
            edge.target,

          name:
            edge.target,

          type:
            "dependency",

          technology:
            "unknown"

        });

        knownNodeIds.add(
          edge.target
        );

      }

    }
  );

  return {
    nodes,
    edges:
      uniqueEdges
  };
}

function calculateFailurePropagation(
  analysis,
  failedService
) {

  const services =
    getServices(analysis);

  const graph =
    buildDependencyGraph(
      analysis
    );

  const affected =
    new Set([
      failedService
    ]);

  let changed = true;

  while (changed) {

    changed = false;

    graph.edges.forEach(
      edge => {

        if (
          affected.has(
            edge.target
          ) &&
          !affected.has(
            edge.source
          )
        ) {

          affected.add(
            edge.source
          );

          changed = true;

        }

      }
    );
  }

  return {

    affectedServices:
      services
        .filter(
          service =>
            affected.has(
              service.name
            )
        )
        .map(
          service =>
            service.name
        ),

    propagationCount:
      Math.max(
        0,
        affected.size - 1
      ),

    propagated:
      affected.size > 1

  };
}

// =====================================================
// BOTTLENECK ENGINE
// =====================================================

function detectBottlenecks(
  analysis
) {

  const services =
    getServices(analysis);

  const findings =
    getFindings(analysis);

  const deployment =
    getDeployment(analysis);

  const bottlenecks = [];

  services.forEach(
    service => {

      const replicas =
        Number(
          service.replicas ||
          service.instances ||
          1
        );

      if (
        (
          service.type ===
            "backend" ||
          service.type ===
            "frontend"
        ) &&
        replicas <= 1
      ) {

        bottlenecks.push({

          service:
            service.name,

          type:
            "single_point_of_failure",

          severity:
            "critical",

          metric:
            "replicas",

          current:
            replicas,

          recommended:
            2,

          reason:
            `Only one ${service.type} instance was detected.`

        });

      }

      if (
        service.type ===
          "worker" &&
        replicas <= 1
      ) {

        bottlenecks.push({

          service:
            service.name,

          type:
            "worker_single_point_of_failure",

          severity:
            "warning",

          metric:
            "replicas",

          current:
            replicas,

          recommended:
            2,

          reason:
            "A single worker can stop background processing."

        });

      }

    }
  );

  const health =
    safeObject(
      deployment.service_health ||
      deployment.health_endpoints_by_service
    );

  services.forEach(
    service => {

      if (
        !health[
          service.name
        ] &&
        !getHealthPath(
          service,
          deployment
        )
      ) {

        bottlenecks.push({

          service:
            service.name,

          type:
            "missing_health_check",

          severity:
            "warning",

          metric:
            "health_check",

          current:
            "not detected",

          recommended:
            "/health",

          reason:
            "Unhealthy instances cannot be safely removed from traffic without a health check."

        });

      }

    }
  );

  findings.forEach(
    finding => {

      if (
        finding?.severity ===
          "critical" ||
        finding?.severity ===
          "warning"
      ) {

        bottlenecks.push({

          service:
            finding.service ||
            "application",

          type:
            "analyzer_finding",

          severity:
            finding.severity,

          metric:
            finding.title ||
            "finding",

          current:
            finding.description ||
            finding.title,

          recommended:
            finding.recommendation ||
            "Review this finding.",

          reason:
            finding.description ||
            "Detected during static analysis."

        });

      }

    }
  );

  return bottlenecks;
}

// =====================================================
// SECURITY / CONFIG NORMALIZATION
// =====================================================

function getSecurityChecks(
  analysis
) {

  const deployment =
    getDeployment(analysis);

  const security =
    safeArray(
      analysis?.security_checks ||
      deployment.security_checks ||
      deployment.security
    );

  const secrets =
    safeArray(
      analysis?.secrets ||
      deployment.secrets ||
      deployment.environment_secrets
    );

  const configFindings =
    safeArray(
      analysis?.configuration_findings ||
      deployment.configuration_findings
    );

  const checks =
    [
      ...security,
      ...configFindings
    ].map(
      item => {

        if (
          typeof item ===
          "string"
        ) {

          return {

            severity:
              "info",

            title:
              item,

            description:
              item

          };

        }

        return {

          severity:
            item?.severity ||
            "info",

          title:
            item?.title ||
            item?.name ||
            "Configuration check",

          description:
            item?.description ||
            "Static configuration check.",

          recommendation:
            item?.recommendation ||
            item?.fix ||
            "Review this configuration."

        };

      }
    );

  return {
    checks,
    secrets
  };
}

// =====================================================
// OPTIMIZATION
// =====================================================

function generateRecommendations(
  analysis
) {

  const services =
    getServices(analysis);

  const findings =
    getFindings(analysis);

  const deployment =
    getDeployment(analysis);

  const dependencies =
    getDependencies(analysis);

  const recommendations = [];

  services.forEach(
    service => {

      const replicas =
        Number(
          service.replicas ||
          service.instances ||
          1
        );

      if (
        service.type ===
          "backend" &&
        replicas < 2
      ) {

        recommendations.push({

          service:
            service.name,

          category:
            "reliability",

          priority:
            "critical",

          action:
            "Scale horizontally",

          current:
            `${replicas} instance${
              replicas === 1
                ? ""
                : "s"
            }`,

          recommended:
            "2+ instances",

          reason:
            `${service.name} is a single point of failure.`

        });

      }

      if (
        service.type ===
          "worker" &&
        replicas < 2
      ) {

        recommendations.push({

          service:
            service.name,

          category:
            "reliability",

          priority:
            "high",

          action:
            "Enable worker redundancy",

          current:
            `${replicas} instance${
              replicas === 1
                ? ""
                : "s"
            }`,

          recommended:
            "2+ instances",

          reason:
            "A worker failure can interrupt background processing."

        });

      }

      if (
        service.type ===
          "frontend" &&
        replicas < 2
      ) {

        recommendations.push({

          service:
            service.name,

          category:
            "availability",

          priority:
            "high",

          action:
            "Enable frontend redundancy",

          current:
            `${replicas} instance${
              replicas === 1
                ? ""
                : "s"
            }`,

          recommended:
            "2+ instances",

          reason:
            "A frontend failure would make the application interface unavailable."

        });

      }

    }
  );

  const health =
    safeObject(
      deployment.service_health ||
      deployment.health_endpoints_by_service
    );

  services.forEach(
    service => {

      if (
        !health[
          service.name
        ] &&
        !getHealthPath(
          service,
          deployment
        )
      ) {

        recommendations.push({

          service:
            service.name,

          category:
            "availability",

          priority:
            "high",

          action:
            "Add health check",

          current:
            "Not detected",

          recommended:
            "/health or service-specific endpoint",

          reason:
            "Health checks let the platform stop routing traffic to unhealthy instances."

        });

      }

    }
  );

  const hasContainers =
    safeArray(
      deployment.dockerfiles
    ).length ||
    safeArray(
      deployment.compose_files
    ).length ||
    safeArray(
      deployment.kubernetes_files
    ).length;

  if (!hasContainers) {

    recommendations.push({

      service:
        "deployment",

      category:
        "deployment",

      priority:
        "medium",

      action:
        "Add explicit container configuration",

      current:
        "Not detected",

      recommended:
        "Container-based deployment",

      reason:
        "Explicit deployment configuration improves reproducibility."

    });

  }

  if (
    safeArray(
      dependencies.databases
    ).length
  ) {

    recommendations.push({

      service:
        "database",

      category:
        "data",

      priority:
        "high",

      action:
        "Review database availability",

      current:
        "Database detected",

      recommended:
        "Evaluate HA, backups and recovery",

      reason:
        "Application redundancy does not automatically make the database highly available."

    });

  }

  const hasWorkers =
    services.some(
      service =>
        service.type ===
        "worker"
    );

  if (
    hasWorkers &&
    !safeArray(
      dependencies.queues
    ).length
  ) {

    recommendations.push({

      service:
        "worker infrastructure",

      category:
        "scalability",

      priority:
        "medium",

      action:
        "Review queue architecture",

      current:
        "No queue detected",

      recommended:
        "Durable message queue",

      reason:
        "A queue can absorb bursts and isolate worker failures."

    });

  }

  findings.forEach(
    finding => {

      if (
        finding?.recommendation
      ) {

        recommendations.push({

          service:
            finding.service ||
            "application",

          category:
            "analysis",

          priority:
            finding.severity ||
            "medium",

          action:
            finding.recommendation,

          current:
            finding.title ||
            "Detected issue",

          recommended:
            finding.recommendation,

          reason:
            finding.description ||
            "Detected during static analysis."

        });

      }

    }
  );

  return recommendations;
}

// =====================================================
// ZEROPS YAML GENERATOR
// =====================================================

function generateZeropsYaml(
  analysis
) {

  const services =
    getServices(analysis);

  const deployment =
    getDeployment(analysis);

  const lines = [

    "# Generated by Zerops Autopilot",

    "# Review service names, build commands and health-check ports before deployment.",

    "",

    "zerops:"

  ];

  services.forEach(
    service => {

      const name =
        String(
          service.name ||
          "app"
        )
          .toLowerCase()
          .replace(
            /[^a-z0-9-]/g,
            "-"
          )
          .slice(
            0,
            25
          ) ||
        "app";

      const tech =
        normalizeTechnology(
          service
        );

      const port =
        getPort(service);

      const start =
        getStartCommand(
          service
        );

      const health =
        getHealthPath(
          service,
          deployment
        );

      lines.push(
        `  - setup: ${name}`
      );

      lines.push(
        "    run:"
      );

      lines.push(
        `      base: ${tech}@latest`
      );

      if (port) {

        lines.push(
          "      ports:"
        );

        lines.push(
          `        - port: ${
            Number(port) ||
            3000
          }`
        );

        lines.push(
          "          protocol: TCP"
        );

        lines.push(
          "          httpSupport: true"
        );

      }

      if (start) {

        lines.push(
          `      start: ${yamlQuote(start)}`
        );

      } else if (
        tech === "nodejs"
      ) {

        lines.push(
          "      start: npm start"
        );

      } else if (
        tech === "python"
      ) {

        lines.push(
          "      start: python main.py"
        );

      }

      if (
        health &&
        port
      ) {

        lines.push(
          "      healthCheck:"
        );

        lines.push(
          "        httpGet:"
        );

        lines.push(
          `          port: ${
            Number(port) ||
            3000
          }`
        );

        lines.push(
          `          path: ${yamlQuote(health)}`
        );

      }

    }
  );

  if (
    !services.length
  ) {

    lines.push(
      "  - setup: app"
    );

    lines.push(
      "    run:"
    );

    lines.push(
      "      base: nodejs@latest"
    );

    lines.push(
      "      start: npm start"
    );

  }

  return (
    lines.join("\n") +
    "\n"
  );
}

// =====================================================
// REPORT
// =====================================================

function buildReport(
  analysis
) {

  const readiness =
    calculateReadiness(
      analysis
    );

  const reliability =
    calculateReliability(
      analysis
    );

  const services =
    getServices(analysis);

  const findings =
    getFindings(analysis);

  const recommendations =
    generateRecommendations(
      analysis
    );

  const security =
    getSecurityChecks(
      analysis
    );

  const lines = [

    "# Zerops Autopilot Reliability Report",

    "",

    `Reliability score: **${reliability}/100**`,

    `Production readiness: **${readiness.overall}/100**`,

    `Production ready: **${
      readiness.productionReady
        ? "Yes"
        : "No"
    }**`,

    "",

    "## Services",

    ...services.map(
      service =>
        `- ${service.name} — ${service.type} — ${service.technology}`
    ),

    "",

    "## Findings",

    ...findings.map(
      finding =>
        `- **${String(
          finding.severity ||
          "info"
        ).toUpperCase()}** ${
          finding.title ||
          "Finding"
        }: ${
          finding.description ||
          ""
        }`
    ),

    "",

    "## Recommendations",

    ...recommendations.map(
      recommendation =>
        `- **${
          recommendation.priority
        }** ${
          recommendation.service
        }: ${
          recommendation.action
        } — ${
          recommendation.reason
        }`
    ),

    "",

    "## Security / Configuration",

    ...security.checks.map(
      check =>
        `- **${String(
          check.severity
        ).toUpperCase()}** ${
          check.title
        }: ${
          check.description
        }`
    ),

    ""

  ];

  return lines.join("\n");
}

// =====================================================
// HEALTH
// =====================================================

app.get(
  "/",
  (req, res) => {

    res.json({

      service:
        "Zerops Autopilot backend",

      status:
        "online",

      version:
        "3.0.0",

      mode:
        "static-analysis",

      ai_required:
        false,

      database_required:
        false,

      analyzer:
        ANALYZER_URL

    });

  }
);

app.get(
  "/api/health",
  (req, res) => {

    res.json({

      status:
        "healthy",

      backend:
        "online",

      analyzer:
        ANALYZER_URL,

      timestamp:
        new Date().toISOString()

    });

  }
);

// =====================================================
// UPLOAD + ANALYSIS
// =====================================================

app.post(
  "/api/upload",
  upload.single("project"),
  async (req, res) => {

    if (!req.file) {

      return res.status(400).json({

        error:
          "No project ZIP archive uploaded."

      });

    }

    try {

      const form =
        new FormData();

      form.append(
        "project",
        fs.createReadStream(
          req.file.path
        ),
        {
          filename:
            req.file.originalname
        }
      );

      const response =
        await axios.post(
          `${ANALYZER_URL}/analyze-project`,
          form,
          {

            headers:
              form.getHeaders(),

            maxContentLength:
              Infinity,

            maxBodyLength:
              Infinity,

            timeout:
              ANALYZER_TIMEOUT

          }
        );

      const analysis =
        response.data;

      const security =
        getSecurityChecks(
          analysis
        );

      return res.json({

        message:
          "Project analyzed successfully",

        project:
          req.file.originalname,

        analysis,

        meta: {

          reliability:
            calculateReliability(
              analysis
            ),

          readiness:
            calculateReadiness(
              analysis
            ),

          securityChecks:
            security.checks.length,

          secretsDetected:
            security.secrets.length,

          bottlenecks:
            detectBottlenecks(
              analysis
            ).length

        }

      });

    } catch (error) {

      console.error(
        "Analyzer error:",
        error.message
      );

      return res.status(
        error.response?.status ||
        500
      ).json({

        error:
          error.response?.data?.error ||
          "Failed to analyze project.",

        details:
          error.message

      });

    } finally {

      if (
        req.file?.path
      ) {

        fs.unlink(
          req.file.path,
          () => {}
        );

      }

    }

  }
);

// =====================================================
// ARCHITECTURE
// =====================================================

app.post(
  "/api/architecture",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const graph =
        buildDependencyGraph(
          req.body.analysis
        );

      res.json({

        status:
          "success",

        architecture:
          graph,

        serviceCount:
          graph.nodes.length,

        dependencyCount:
          graph.edges.length

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to generate architecture graph.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// BOTTLENECKS
// =====================================================

app.post(
  "/api/bottlenecks",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const bottlenecks =
        detectBottlenecks(
          req.body.analysis
        );

      res.json({

        status:
          "success",

        bottlenecks,

        summary: {

          total:
            bottlenecks.length,

          critical:
            bottlenecks.filter(
              item =>
                item.severity ===
                "critical"
            ).length,

          warnings:
            bottlenecks.filter(
              item =>
                item.severity ===
                "warning"
            ).length

        }

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to detect bottlenecks.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// SECURITY / ENVIRONMENT
// =====================================================

app.post(
  "/api/security",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const result =
        getSecurityChecks(
          req.body.analysis
        );

      res.json({

        status:
          "success",

        ...result

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to generate security checks.",

        details:
          error.message

      });

    }

  }
);

app.post(
  "/api/environment",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const deployment =
        getDeployment(
          req.body.analysis
        );

      const environment =
        safeArray(
          req.body.analysis
            ?.environment_variables ||
          deployment.environment_variables ||
          deployment.env_variables
        );

      const secrets =
        safeArray(
          req.body.analysis?.secrets ||
          deployment.secrets ||
          deployment.environment_secrets
        );

      res.json({

        status:
          "success",

        environment,

        secrets,

        secretValuesReturned:
          false

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to inspect environment configuration.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// READINESS
// =====================================================

app.post(
  "/api/readiness",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      res.json({

        status:
          "success",

        readiness:
          calculateReadiness(
            req.body.analysis
          )

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to calculate production readiness.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// FAILURE SIMULATOR
// =====================================================

app.post(
  "/api/simulate",
  (req, res) => {

    try {

      const {
        failure,
        analysis
      } = req.body || {};

      if (!failure) {

        return res.status(
          400
        ).json({

          error:
            "Failure type is required."

        });

      }

      if (!analysis) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const services =
        getServices(
          analysis
        );

      const backends =
        services.filter(
          service =>
            service.type ===
            "backend"
        );

      const workers =
        services.filter(
          service =>
            service.type ===
            "worker"
        );

      // =================================================
      // TRAFFIC SPIKE
      // =================================================

      if (
        failure ===
        "traffic"
      ) {

        const affectedServices =
          backends.length
            ? serviceNames(
                backends
              )
            : serviceNames(
                services
              );

        const critical =
          backends.length <= 1;

        return res.json({

          status:
            "simulated",

          failure:
            "Traffic Spike ×10",

          type:
            "traffic_spike",

          affectedServices,

          severity:
            critical
              ? "critical"
              : "warning",

          reliabilityScore:
            critical
              ? 48
              : 70,

          message:
            "Incoming traffic increased by approximately 10×.",

          impact: [

            "Request volume increases significantly.",

            "Response latency may increase.",

            critical
              ? "A single backend instance may become saturated."
              : "Backend capacity may require additional scaling."

          ],

          recommendation:
            critical
              ? "Scale backend instances horizontally and distribute traffic between them."
              : "Monitor capacity and scale backend instances when required."

        });

      }

      // =================================================
      // CASCADING FAILURE
      // =================================================

      if (
        failure ===
        "cascading"
      ) {

        const target =
          backends[0] ||
          workers[0] ||
          services[0];

        if (!target) {

          return res.status(
            404
          ).json({

            error:
              "No services were detected for cascading-failure simulation."

          });

        }

        const propagation =
          calculateFailurePropagation(
            analysis,
            target.name
          );

        return res.json({

          status:
            "simulated",

          failure:
            "Cascading Failure",

          type:
            "cascading_failure",

          rootCause:
            target.name,

          affectedServices:
            propagation.affectedServices,

          propagation,

          severity:
            propagation.propagated
              ? "critical"
              : "warning",

          reliabilityScore:
            propagation.propagated
              ? 35
              : 65,

          impact:
            propagation.propagated
              ? [
                  "The root service is unavailable.",

                  `${propagation.propagationCount} dependent service(s) are affected by the inferred dependency graph.`
                ]
              : [
                  "The root service is unavailable.",

                  "No dependent service propagation was inferred."
                ],

          recommendation:
            "Remove single points of failure, add health-aware routing, and isolate asynchronous work with durable queues where applicable."

        });

      }

      // =================================================
      // SERVICE FAILURE
      // =================================================

      const target =
        serviceByName(
          services,
          failure
        );

      if (!target) {

        return res.status(
          404
        ).json({

          error:
            `Service '${failure}' was not found in the uploaded project.`

        });

      }

      const propagation =
        calculateFailurePropagation(
          analysis,
          target.name
        );

      const isBackend =
        target.type ===
        "backend";

      const isFrontend =
        target.type ===
        "frontend";

      const isWorker =
        target.type ===
        "worker";

      return res.json({

        status:
          "simulated",

        failure:
          `${target.name} Failure`,

        type:
          "service_failure",

        affectedServices:
          propagation.affectedServices,

        propagation,

        severity:
          isBackend ||
          isFrontend
            ? "critical"
            : "warning",

        reliabilityScore:
          isBackend
            ? (
                backends.length === 1
                  ? 35
                  : 70
              )
            : isFrontend
              ? 40
              : 72,

        message:
          `The ${target.name} service is unavailable.`,

        impact:
          isFrontend

            ? [

                "Users cannot access the application interface.",

                "Backend services may remain operational.",

                propagation.propagated
                  ? "Dependency propagation was detected."
                  : "No downstream dependency propagation was detected."

              ]

            : isWorker

              ? [

                  `${target.name} processing stops.`,

                  propagation.propagated
                    ? "Dependent services may also be affected."
                    : "Other services may continue operating."

                ]

              : [

                  `Requests may not reach ${target.name}.`,

                  workers.length
                    ? "Dependent worker processing may become unavailable."
                    : "No worker services were detected.",

                  propagation.propagated
                    ? `${propagation.propagationCount} dependent service(s) may also be affected.`
                    : "No cascading dependency failure was detected."

                ],

        recommendation:
          isWorker

            ? `Deploy redundant ${target.name} workers and use a durable queue for fault isolation.`

            : `Run multiple ${target.name} instances and configure health checks.`

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to simulate failure.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// OPTIMIZATION ENGINE
// =====================================================

app.post(
  "/api/optimize",
  (req, res) => {

    try {

      const {
        analysis
      } = req.body || {};

      if (!analysis) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const currentReliability =
        calculateReliability(
          analysis
        );

      const recommendations =
        generateRecommendations(
          analysis
        );

      const bottlenecks =
        detectBottlenecks(
          analysis
        );

      const readiness =
        calculateReadiness(
          analysis
        );

      const services =
        getServices(
          analysis
        );

      const deployment =
        getDeployment(
          analysis
        );

      const architecture = {

        services:
          services.map(
            service => {

              const optimized = {

                name:
                  service.name,

                type:
                  service.type,

                technology:
                  service.technology,

                replicas:
                  [
                    "backend",
                    "worker",
                    "frontend"
                  ].includes(
                    service.type
                  )
                    ? 2
                    : Number(
                        service.replicas ||
                        1
                      )

              };

              const port =
                getPort(
                  service
                );

              const startCommand =
                getStartCommand(
                  service
                );

              const healthPath =
                getHealthPath(
                  service,
                  deployment
                );

              if (port) {

                optimized.port =
                  port;

              }

              if (
                startCommand
              ) {

                optimized.startCommand =
                  startCommand;

              }

              if (
                healthPath
              ) {

                optimized.healthCheck =
                  healthPath;

              }

              return optimized;

            }
          ),

        dependencyGraph:
          buildDependencyGraph(
            analysis
          )

      };

      const critical =
        getFindings(
          analysis
        ).filter(
          finding =>
            finding?.severity ===
            "critical"
        ).length;

      const warnings =
        getFindings(
          analysis
        ).filter(
          finding =>
            finding?.severity ===
            "warning"
        ).length;

      const optimizedReliability =
        Math.min(

          100,

          currentReliability +

          critical * 30 +

          warnings * 10 +

          (
            readiness.overall < 80
              ? 5
              : 0
          )

        );

      const security =
        getSecurityChecks(
          analysis
        );

      res.json({

        status:
          "optimized",

        currentReliability,

        optimizedReliability,

        improvement:
          optimizedReliability -
          currentReliability,

        productionReadiness:
          readiness,

        architecture,

        bottlenecks,

        recommendations,

        security,

        zeropsYml:
          generateZeropsYaml(
            analysis
          ),

        report:
          buildReport(
            analysis
          )

      });

    } catch (error) {

      console.error(
        "Optimization error:",
        error
      );

      res.status(
        500
      ).json({

        error:
          "Failed to generate optimized architecture.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// ZEROPS CONFIGURATION
// =====================================================

app.post(
  "/api/zerops",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const zeropsYml =
        generateZeropsYaml(
          req.body.analysis
        );

      res.json({

        status:
          "success",

        filename:
          "zerops.yaml",

        zeropsYml

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to generate Zerops configuration.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// REPORT
// =====================================================

app.post(
  "/api/report",
  (req, res) => {

    try {

      if (
        !req.body?.analysis
      ) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      res.json({

        status:
          "success",

        filename:
          "zerops-autopilot-report.md",

        report:
          buildReport(
            req.body.analysis
          )

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to generate report.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// PROJECT SUMMARY
// =====================================================

app.post(
  "/api/summary",
  (req, res) => {

    try {

      const {
        analysis
      } = req.body || {};

      if (!analysis) {

        return res.status(
          400
        ).json({

          error:
            "Analysis data is required."

        });

      }

      const services =
        getServices(
          analysis
        );

      const dependencies =
        getDependencies(
          analysis
        );

      const deployment =
        getDeployment(
          analysis
        );

      const findings =
        getFindings(
          analysis
        );

      const graph =
        buildDependencyGraph(
          analysis
        );

      const readiness =
        calculateReadiness(
          analysis
        );

      const security =
        getSecurityChecks(
          analysis
        );

      res.json({

        status:
          "success",

        summary: {

          services:
            services.length,

          serviceNames:
            serviceNames(
              services
            ),

          dependencies:
            graph.edges.length,

          databases:
            safeArray(
              dependencies.databases
            ).length,

          queues:
            safeArray(
              dependencies.queues
            ).length,

          caches:
            safeArray(
              dependencies.caches
            ).length,

          objectStorage:
            safeArray(
              dependencies.object_storage
            ).length,

          findings:
            findings.length,

          criticalFindings:
            findings.filter(
              finding =>
                finding.severity ===
                "critical"
            ).length,

          warnings:
            findings.filter(
              finding =>
                finding.severity ===
                "warning"
            ).length,

          dockerfiles:
            safeArray(
              deployment.dockerfiles
            ).length,

          ciCd:
            safeArray(
              deployment.ci_cd ||
              deployment.cicd
            ).length,

          iac:
            safeArray(
              deployment.infrastructure_as_code ||
              deployment.iac
            ).length,

          securityChecks:
            security.checks.length,

          secretsDetected:
            security.secrets.length

        },

        reliability:
          calculateReliability(
            analysis
          ),

        productionReadiness:
          readiness,

        architecture:
          graph

      });

    } catch (error) {

      res.status(
        500
      ).json({

        error:
          "Failed to generate project summary.",

        details:
          error.message

      });

    }

  }
);

// =====================================================
// ERROR HANDLER
// =====================================================

app.use(
  (
    error,
    req,
    res,
    next
  ) => {

    console.error(
      "Unhandled error:",
      error
    );

    if (
      error instanceof
        multer.MulterError &&
      error.code ===
        "LIMIT_FILE_SIZE"
    ) {

      return res.status(
        413
      ).json({

        error:
          "Project archive is too large. Maximum size is 100 MB."

      });

    }

    if (
      error.message ===
      "Only ZIP project archives are supported."
    ) {

      return res.status(
        400
      ).json({

        error:
          error.message

      });

    }

    return res.status(
      500
    ).json({

      error:
        error.message ||
        "Internal server error."

    });

  }
);

// =====================================================
// SERVER
// =====================================================

app.listen(
  PORT,
  () => {

    console.log(
      `Zerops Autopilot backend running on port ${PORT}`
    );

    console.log(
      `Analyzer URL: ${ANALYZER_URL}`
    );

    console.log(
      "Mode: static-analysis | AI key: not required | database: not required"
    );

  }
);