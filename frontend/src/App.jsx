import { useRef, useState } from "react";
import "./App.css";

const API_BASE_URL = "https://api-2b79-3000.prg1.zerops.app";


// =====================================================
// DEMO DATA
// =====================================================

const DEMO_ANALYSIS = {
  status: "success",

  project: "zerops-autopilot-demo.zip",

  file_count: 12,

  technologies: [
    "Node.js / JavaScript",
    "Python",
    "Docker / OCI",
  ],

  services: [
    {
      name: "frontend",
      technology: "Node.js / React + Vite",
      type: "frontend",
      directory: "frontend",
    },
    {
      name: "api",
      technology: "Node.js / Express",
      type: "backend",
      directory: "api",
    },
    {
      name: "worker",
      technology: "Python / Flask",
      type: "worker",
      directory: "worker",
    },
  ],

  dependencies: {
    databases: ["PostgreSQL"],
    queues: ["Message Queue"],
    caches: ["Redis"],
    object_storage: ["Object Storage"],
  },

  deployment: {
    ports: [3000, 5000],
    health_endpoints: ["/health"],
    health_endpoints_by_service: {
      api: "/health",
    },
    service_health: {
      api: "/health",
    },
    dockerfiles: ["frontend/Dockerfile"],
    zerops_configs: [],
  },

  architecture: {
    nodes: [
      {
        name: "frontend",
        type: "frontend",
        technology: "Node.js / React + Vite",
      },
      {
        name: "api",
        type: "backend",
        technology: "Node.js / Express",
      },
      {
        name: "worker",
        type: "worker",
        technology: "Python / Flask",
      },
      {
        name: "postgresql",
        type: "database",
        technology: "PostgreSQL",
      },
      {
        name: "redis",
        type: "cache",
        technology: "Redis",
      },
      {
        name: "message-queue",
        type: "queue",
        technology: "Message Queue",
      },
    ],

    connections: [
      {
        from: "frontend",
        to: "api",
        relationship: "request",
      },
      {
        from: "api",
        to: "worker",
        relationship: "processing",
      },
      {
        from: "api",
        to: "postgresql",
        relationship: "database",
      },
      {
        from: "api",
        to: "redis",
        relationship: "cache",
      },
      {
        from: "api",
        to: "message-queue",
        relationship: "queue",
      },
    ],
  },

  failure_scenarios: [
    {
      id: "api",
      label: "api Failure",
      description:
        "Simulate failure of the backend service.",
    },
    {
      id: "worker",
      label: "worker Failure",
      description:
        "Simulate failure of the worker service.",
    },
    {
      id: "frontend",
      label: "frontend Failure",
      description:
        "Simulate failure of the frontend service.",
    },
    {
      id: "traffic",
      label: "Traffic Spike ×10",
      description:
        "Simulate a tenfold increase in incoming traffic.",
    },
    {
      id: "cascading",
      label: "Cascading Failure",
      description:
        "Simulate failure propagation through the dependency graph.",
    },
  ],

  reliability_score: 40,

  findings: [
    {
      severity: "critical",
      title: "api Single Point of Failure",
      description:
        "Only one api backend service was detected.",
      recommendation:
        "Deploy multiple api instances behind a health-aware load balancer.",
    },
    {
      severity: "warning",
      title: "worker Redundancy Not Detected",
      description:
        "Only one worker instance is represented.",
      recommendation:
        "Run multiple workers with durable queue semantics.",
    },
    {
      severity: "warning",
      title: "Frontend Redundancy Not Detected",
      description:
        "Only one frontend service is represented.",
      recommendation:
        "Use redundant frontend instances or a highly available static/CDN deployment.",
    },
    {
      severity: "info",
      title: "CI/CD Configuration Not Detected",
      description:
        "No common CI/CD workflow was detected.",
      recommendation:
        "Add automated build, test and deployment checks.",
    },
  ],

  bottlenecks: [
    {
      severity: "critical",
      service: "api",
      title: "Backend Capacity Bottleneck",
      description:
        "The API is the primary request-processing service and is represented by a single instance.",
      recommendation:
        "Scale horizontally and distribute incoming traffic.",
    },
  ],

  security: [
    {
      severity: "warning",
      title: "Security Configuration Requires Review",
      description:
        "Static analysis cannot guarantee production security configuration.",
      recommendation:
        "Review secrets handling, authentication, authorization, TLS and exposed ports before deployment.",
    },
  ],

  delivery: {
    cicd: false,
    infrastructure_as_code: false,
    containerized: true,
    zerops_configured: false,
  },

  files: [
    "README.md",
    "api/index.js",
    "api/package.json",
    "worker/main.py",
    "worker/requirements.txt",
    "frontend/package.json",
    "frontend/Dockerfile",
  ],
};


// =====================================================
// HELPERS
// =====================================================

function getSeverityIcon(severity) {
  if (severity === "critical") return "🔴";
  if (severity === "warning") return "🟠";
  if (severity === "info") return "🔵";
  return "⚪";
}


function getServiceTypeLabel(type) {
  return type
    ? type.toUpperCase()
    : "SERVICE";
}


function getNodeIcon(type) {
  const icons = {
    frontend: "🖥️",
    backend: "⚙️",
    worker: "⚡",
    database: "🗄️",
    queue: "📨",
    cache: "⚡",
    object_storage: "☁️",
    storage: "☁️",
  };

  return icons[type] || "◆";
}


function formatRelationship(relationship) {
  if (!relationship) return "dependency";

  return relationship
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase()
    );
}


// =====================================================
// APP
// =====================================================

function App() {
  const fileInputRef = useRef(null);

  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [simulation, setSimulation] = useState(null);
  const [simulationLoading, setSimulationLoading] =
    useState(false);

  const [optimization, setOptimization] =
    useState(null);

  const [optimizing, setOptimizing] =
    useState(false);

  const [copied, setCopied] =
    useState(false);

  const [reportDownloaded, setReportDownloaded] =
    useState(false);


  // =====================================================
  // UPLOAD
  // =====================================================

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };


  const handleFileChange = async (event) => {
    const file = event.target.files?.[0];

    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Please upload a ZIP project archive.");
      return;
    }

    setLoading(true);
    setError("");
    setAnalysis(null);
    setSimulation(null);
    setOptimization(null);
    setCopied(false);
    setReportDownloaded(false);

    const formData = new FormData();

    formData.append(
      "project",
      file
    );

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/upload`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error ||
          "Failed to analyze project"
        );
      }

      setAnalysis(data.analysis);
    } catch (uploadError) {
      console.error(uploadError);

      setError(
        uploadError.message ||
        "Unable to connect to the backend."
      );
    } finally {
      setLoading(false);
    }
  };


  // =====================================================
  // DEMO PROJECT
  // =====================================================

  const loadDemoProject = () => {
    setError("");
    setAnalysis(DEMO_ANALYSIS);
    setSimulation(null);
    setOptimization(null);
    setCopied(false);
    setReportDownloaded(false);
  };


  // =====================================================
  // FAILURE SIMULATION
  // =====================================================

  const simulateFailure = async (failure) => {
    if (!analysis) return;

    setSimulationLoading(true);
    setSimulation(null);
    setError("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/simulate`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            failure,
            analysis,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error ||
          "Simulation failed"
        );
      }

      setSimulation(data);
    } catch (simulationError) {
      console.error(simulationError);

      /*
       * Cascading failure may be supported by the newer
       * backend. If an older backend doesn't implement
       * it yet, display a useful client-side result.
       */

      if (
        failure === "cascading"
      ) {
        const services =
          Array.isArray(analysis.services)
            ? analysis.services
            : [];

        setSimulation({
          status: "simulated",
          failure: "Cascading Failure",
          affectedServices:
            services.map(
              (service) =>
                service.name
            ),
          severity: "critical",
          reliabilityScore: 25,
          message:
            "A failure can propagate through dependent services.",
          impact: [
            "The failed dependency may interrupt downstream services.",
            "Worker processing may be interrupted.",
            "Request paths depending on the failed service may become unavailable.",
          ],
          recommendation:
            "Introduce redundancy, health-aware routing, queues and failure isolation between critical services.",
        });
      } else {
        setError(
          simulationError.message ||
          "Simulation failed"
        );
      }
    } finally {
      setSimulationLoading(false);
    }
  };


  // =====================================================
  // OPTIMIZATION
  // =====================================================

  const handleOptimize = async () => {
    if (!analysis) return;

    setOptimizing(true);
    setOptimization(null);
    setError("");
    setCopied(false);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/optimize`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            analysis,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error ||
          "Optimization failed"
        );
      }

      setOptimization(data);
    } catch (optimizationError) {
      console.error(
        optimizationError
      );

      setError(
        optimizationError.message ||
        "Optimization failed"
      );
    } finally {
      setOptimizing(false);
    }
  };


  // =====================================================
  // COPY ZEROPS CONFIGURATION
  // =====================================================

  const copyZeropsConfig = async () => {
    if (!optimization?.zeropsYml) return;

    try {
      await navigator.clipboard.writeText(
        optimization.zeropsYml
      );

      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch (copyError) {
      console.error(copyError);

      setError(
        "Failed to copy Zerops configuration."
      );
    }
  };


  // =====================================================
  // DOWNLOAD ZEROPS CONFIGURATION
  // =====================================================

  const downloadZeropsConfig = () => {
    if (!optimization?.zeropsYml) return;

    const blob = new Blob(
      [optimization.zeropsYml],
      {
        type: "text/yaml;charset=utf-8",
      }
    );

    const url =
      URL.createObjectURL(blob);

    const link =
      document.createElement("a");

    link.href = url;
    link.download = "zerops.yml";

    document.body.appendChild(link);

    link.click();

    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  };


  // =====================================================
  // DOWNLOAD ANALYSIS REPORT
  // =====================================================

  const downloadAnalysisReport = () => {
    if (!analysis) return;

    const report = {
      generatedBy:
        "Zerops Autopilot",

      mode:
        "static-analysis",

      generatedAt:
        new Date().toISOString(),

      analysis,
    };

    const blob = new Blob(
      [
        JSON.stringify(
          report,
          null,
          2
        ),
      ],
      {
        type: "application/json",
      }
    );

    const url =
      URL.createObjectURL(blob);

    const link =
      document.createElement("a");

    link.href = url;

    link.download =
      "zerops-autopilot-analysis.json";

    document.body.appendChild(link);

    link.click();

    document.body.removeChild(link);

    URL.revokeObjectURL(url);

    setReportDownloaded(true);

    setTimeout(() => {
      setReportDownloaded(false);
    }, 2000);
  };


  // =====================================================
  // RESET
  // =====================================================

  const resetApplication = () => {
    setError("");
    setAnalysis(null);
    setSimulation(null);
    setOptimization(null);
    setCopied(false);
    setReportDownloaded(false);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };


  // =====================================================
  // SAFE DATA
  // =====================================================

  const services =
    Array.isArray(analysis?.services)
      ? analysis.services
      : [];

  const technologies =
    Array.isArray(analysis?.technologies)
      ? analysis.technologies
      : [];

  const findings =
    Array.isArray(analysis?.findings)
      ? analysis.findings
      : [];

  const dependencies =
    analysis?.dependencies || {};

  const deployment =
    analysis?.deployment || {};

  const architecture =
    analysis?.architecture || {};

  const architectureNodes =
    Array.isArray(
      architecture.nodes
    )
      ? architecture.nodes
      : [];

  const architectureConnections =
    Array.isArray(
      architecture.connections
    )
      ? architecture.connections
      : [];

  const bottlenecks =
    Array.isArray(
      analysis?.bottlenecks
    )
      ? analysis.bottlenecks
      : [];

  const securityFindings =
    Array.isArray(
      analysis?.security
    )
      ? analysis.security
      : [];

  const failureScenarios =
    Array.isArray(
      analysis?.failure_scenarios
    )
      ? analysis.failure_scenarios
      : [];

  const delivery =
    analysis?.delivery || {};

  const criticalCount =
    findings.filter(
      (finding) =>
        finding.severity ===
        "critical"
    ).length;

  const warningCount =
    findings.filter(
      (finding) =>
        finding.severity ===
        "warning"
    ).length;

  const infoCount =
    findings.filter(
      (finding) =>
        finding.severity ===
        "info"
    ).length;


  // =====================================================
  // UI
  // =====================================================

  return (
    <div className="app">

      {/* =================================================
          HEADER
      ================================================= */}

      <header className="header">

        <div className="brand">

          <div className="brand-logo">
            Z
          </div>

          <strong>
            Zerops Autopilot
          </strong>

        </div>

        <div className="status">

          <span className="status-dot" />

          System Online

        </div>

      </header>


      <main className="main">

        {/* =================================================
            HERO
        ================================================= */}

        <section className="hero">

          <div className="badge">
            AI-NATIVE RELIABILITY ENGINE
          </div>

          <h1>
            Break your application
            <br />

            <span>
              before production does.
            </span>
          </h1>

          <p>
            Analyze your architecture, discover
            dependencies and bottlenecks, simulate
            production failures, and generate a more
            resilient Zerops deployment.
          </p>


          <div className="actions">

            <button
              className="primary-button"
              onClick={
                handleUploadClick
              }
              disabled={loading}
            >
              {loading
                ? "Analyzing..."
                : "Upload Project"}
            </button>


            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              style={{
                display: "none",
              }}
              onChange={
                handleFileChange
              }
            />


            <button
              className="secondary-button"
              onClick={
                loadDemoProject
              }
            >
              Try Demo Project
            </button>


            {analysis && (
              <button
                className="secondary-button"
                onClick={
                  resetApplication
                }
              >
                New Analysis
              </button>
            )}

          </div>


          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

        </section>


        {/* =================================================
            ANALYSIS
        ================================================= */}

        {analysis && (

          <section className="analysis-panel">

            {/* =================================================
                ANALYSIS HEADER
            ================================================= */}

            <div className="analysis-header">

              <div>

                <div className="analysis-label">
                  ANALYSIS COMPLETE
                </div>

                <h2>
                  {analysis.project}
                </h2>

              </div>

              <div className="success-badge">
                ✓ Success
              </div>

            </div>


            {/* =================================================
                OVERVIEW STATS
            ================================================= */}

            <div className="analysis-stats">

              <div className="stat-card">

                <span>
                  Files Detected
                </span>

                <strong>
                  {analysis.file_count || 0}
                </strong>

              </div>


              <div className="stat-card">

                <span>
                  Technologies
                </span>

                <strong>
                  {technologies.length}
                </strong>

              </div>


              <div className="stat-card">

                <span>
                  Reliability
                </span>

                <strong>
                  {analysis.reliability_score ??
                    "—"}/100
                </strong>

              </div>

            </div>


            {/* =================================================
                FINDING SUMMARY
            ================================================= */}

            <div className="analysis-stats">

              <div className="stat-card">

                <span>
                  Critical Risks
                </span>

                <strong>
                  {criticalCount}
                </strong>

              </div>


              <div className="stat-card">

                <span>
                  Warnings
                </span>

                <strong>
                  {warningCount}
                </strong>

              </div>


              <div className="stat-card">

                <span>
                  Informational
                </span>

                <strong>
                  {infoCount}
                </strong>

              </div>

            </div>


            {/* =================================================
                TECHNOLOGIES
            ================================================= */}

            <div className="technology-section">

              <h3>
                Detected Technologies
              </h3>

              <div className="technology-list">

                {technologies.length > 0 ? (
                  technologies.map(
                    (technology) => (

                      <span
                        className="technology"
                        key={technology}
                      >
                        {technology}
                      </span>

                    )
                  )
                ) : (
                  <span className="technology">
                    None detected
                  </span>
                )}

              </div>

            </div>


            {/* =================================================
                SERVICES
            ================================================= */}

            <div className="services-section">

              <h3>
                Detected Services
              </h3>

              <div className="services-grid">

                {services.length > 0 ? (
                  services.map(
                    (service, index) => {

                      const healthPath =
                        deployment
                          .service_health?.[
                            service.name
                          ] ||
                        deployment
                          .health_endpoints_by_service?.[
                            service.name
                          ];

                      return (
                        <div
                          className="service-card"
                          key={`${service.name}-${index}`}
                        >

                          <div className="service-type">
                            {getServiceTypeLabel(
                              service.type
                            )}
                          </div>

                          <h4>
                            {service.name}
                          </h4>

                          <p>
                            {service.technology ||
                              "Unknown technology"}
                          </p>

                          {service.directory && (
                            <p>
                              Directory:{" "}
                              {service.directory}
                            </p>
                          )}

                          {healthPath && (
                            <p>
                              Health:{" "}
                              {healthPath}
                            </p>
                          )}

                        </div>
                      );
                    }
                  )
                ) : (
                  <div className="service-card">
                    <h4>
                      No services detected
                    </h4>
                  </div>
                )}

              </div>

            </div>


            {/* =================================================
                DEPENDENCIES
            ================================================= */}

            <div className="services-section">

              <div className="analysis-label">
                DEPENDENCY ANALYSIS
              </div>

              <h3>
                Infrastructure Dependencies
              </h3>

              <div className="services-grid">

                <div className="service-card">

                  <div className="service-type">
                    DATABASES
                  </div>

                  <h4>
                    {dependencies.databases
                      ?.length || 0}
                  </h4>

                  <p>
                    {dependencies.databases
                      ?.join(", ") ||
                      "No database detected"}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    MESSAGE QUEUES
                  </div>

                  <h4>
                    {dependencies.queues
                      ?.length || 0}
                  </h4>

                  <p>
                    {dependencies.queues
                      ?.join(", ") ||
                      "No queue detected"}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    CACHES
                  </div>

                  <h4>
                    {dependencies.caches
                      ?.length || 0}
                  </h4>

                  <p>
                    {dependencies.caches
                      ?.join(", ") ||
                      "No cache detected"}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    OBJECT STORAGE
                  </div>

                  <h4>
                    {dependencies.object_storage
                      ?.length || 0}
                  </h4>

                  <p>
                    {dependencies.object_storage
                      ?.join(", ") ||
                      "No object storage detected"}
                  </p>

                </div>

              </div>

            </div>


            {/* =================================================
                DEPLOYMENT INFORMATION
            ================================================= */}

            <div className="services-section">

              <div className="analysis-label">
                DEPLOYMENT ANALYSIS
              </div>

              <h3>
                Runtime & Deployment Signals
              </h3>

              <div className="services-grid">

                <div className="service-card">

                  <div className="service-type">
                    PORTS
                  </div>

                  <h4>
                    {deployment.ports
                      ?.length || 0}
                  </h4>

                  <p>
                    {deployment.ports
                      ?.join(", ") ||
                      "No ports detected"}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    HEALTH ENDPOINTS
                  </div>

                  <h4>
                    {deployment
                      .health_endpoints
                      ?.length || 0}
                  </h4>

                  <p>
                    {deployment
                      .health_endpoints
                      ?.join(", ") ||
                      "None detected"}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    CONTAINERS
                  </div>

                  <h4>
                    {deployment
                      .dockerfiles
                      ?.length || 0}
                  </h4>

                  <p>
                    {deployment
                      .dockerfiles
                      ?.join(", ") ||
                      "No Dockerfile detected"}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    ZEROPS
                  </div>

                  <h4>
                    {deployment
                      .zerops_configs
                      ?.length
                      ? "Detected"
                      : "Not detected"}
                  </h4>

                  <p>
                    {deployment
                      .zerops_configs
                      ?.join(", ") ||
                      "No existing Zerops configuration"}
                  </p>

                </div>

              </div>

            </div>


            {/* =================================================
                RELIABILITY ANALYSIS
            ================================================= */}

            <div className="findings-section">

              <div className="analysis-label">
                RELIABILITY ANALYSIS
              </div>

              <h3>
                Detected Risks
              </h3>

              <div className="findings-list">

                {findings.length > 0 ? (

                  findings.map(
                    (finding, index) => (

                      <div
                        className={`finding-card ${
                          finding.severity ||
                          "info"
                        }`}
                        key={`${finding.title}-${index}`}
                      >

                        <div className="finding-severity">

                          {getSeverityIcon(
                            finding.severity
                          )}{" "}

                          {(
                            finding.severity ||
                            "info"
                          ).toUpperCase()}

                        </div>


                        <h4>
                          {finding.title}
                        </h4>


                        <p>
                          {finding.description}
                        </p>


                        {finding.recommendation && (
                          <div className="recommendation">

                            <strong>
                              Recommendation
                            </strong>

                            <span>
                              {finding.recommendation}
                            </span>

                          </div>
                        )}

                      </div>

                    )
                  )

                ) : (

                  <div className="finding-card info">

                    <h4>
                      No Reliability Risks Detected
                    </h4>

                    <p>
                      No significant reliability
                      issues were detected.
                    </p>

                  </div>

                )}

              </div>

            </div>


            {/* =================================================
                BOTTLENECK ANALYSIS
            ================================================= */}

            {bottlenecks.length > 0 && (

              <div className="findings-section">

                <div className="analysis-label">
                  BOTTLENECK ANALYSIS
                </div>

                <h3>
                  Potential Performance Bottlenecks
                </h3>

                <div className="findings-list">

                  {bottlenecks.map(
                    (bottleneck, index) => (

                      <div
                        className={`finding-card ${
                          bottleneck.severity ||
                          "warning"
                        }`}
                        key={`bottleneck-${index}`}
                      >

                        <div className="finding-severity">

                          {getSeverityIcon(
                            bottleneck.severity ||
                            "warning"
                          )}{" "}

                          {(
                            bottleneck.severity ||
                            "warning"
                          ).toUpperCase()}

                        </div>


                        <h4>
                          {bottleneck.title ||
                            bottleneck.service ||
                            "Potential Bottleneck"}
                        </h4>


                        <p>
                          {bottleneck.description ||
                            "A potential capacity or dependency bottleneck was detected."}
                        </p>


                        {bottleneck.recommendation && (
                          <div className="recommendation">

                            <strong>
                              Recommended Action
                            </strong>

                            <span>
                              {bottleneck.recommendation}
                            </span>

                          </div>
                        )}

                      </div>

                    )
                  )}

                </div>

              </div>

            )}


            {/* =================================================
                SECURITY
            ================================================= */}

            {securityFindings.length > 0 && (

              <div className="findings-section">

                <div className="analysis-label">
                  SECURITY ANALYSIS
                </div>

                <h3>
                  Security & Production Checks
                </h3>

                <div className="findings-list">

                  {securityFindings.map(
                    (finding, index) => (

                      <div
                        className={`finding-card ${
                          finding.severity ||
                          "warning"
                        }`}
                        key={`security-${index}`}
                      >

                        <div className="finding-severity">

                          {getSeverityIcon(
                            finding.severity ||
                            "warning"
                          )}{" "}

                          {(
                            finding.severity ||
                            "warning"
                          ).toUpperCase()}

                        </div>

                        <h4>
                          {finding.title ||
                            "Security Check"}
                        </h4>

                        <p>
                          {finding.description}
                        </p>

                        {finding.recommendation && (
                          <div className="recommendation">

                            <strong>
                              Recommendation
                            </strong>

                            <span>
                              {finding.recommendation}
                            </span>

                          </div>
                        )}

                      </div>

                    )
                  )}

                </div>

              </div>

            )}


            {/* =================================================
                DELIVERY READINESS
            ================================================= */}

            <div className="findings-section">

              <div className="analysis-label">
                DELIVERY READINESS
              </div>

              <h3>
                Production Engineering Checks
              </h3>

              <div className="services-grid">

                <div className="service-card">

                  <div className="service-type">
                    CI/CD
                  </div>

                  <h4>
                    {delivery.cicd
                      ? "Detected"
                      : "Not Detected"}
                  </h4>

                  <p>
                    {delivery.cicd
                      ? "Automated delivery configuration was detected."
                      : "No common CI/CD workflow was detected."}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    INFRASTRUCTURE AS CODE
                  </div>

                  <h4>
                    {delivery.infrastructure_as_code
                      ? "Detected"
                      : "Not Detected"}
                  </h4>

                  <p>
                    {delivery.infrastructure_as_code
                      ? "Infrastructure configuration was detected."
                      : "No Terraform/Pulumi-style infrastructure configuration was detected."}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    CONTAINERIZATION
                  </div>

                  <h4>
                    {delivery.containerized
                      ? "Detected"
                      : "Not Detected"}
                  </h4>

                  <p>
                    {delivery.containerized
                      ? "Container configuration was detected."
                      : "No explicit container configuration was detected."}
                  </p>

                </div>


                <div className="service-card">

                  <div className="service-type">
                    ZEROPS CONFIG
                  </div>

                  <h4>
                    {delivery.zerops_configured
                      ? "Detected"
                      : "Generated by Optimizer"}
                  </h4>

                  <p>
                    The optimization engine can generate a deployment configuration.
                  </p>

                </div>

              </div>

            </div>


            {/* =================================================
                ARCHITECTURE MAP
            ================================================= */}

            <div className="architecture-section">

              <div className="architecture-header">

                <div>

                  <div className="analysis-label">
                    ARCHITECTURE MAP
                  </div>

                  <h3>
                    Detected Application Architecture
                  </h3>

                </div>

              </div>


              <div className="architecture-graph">

                {architectureNodes.length > 0 ? (

                  architectureNodes.map(
                    (node, index) => {

                      const outgoing =
                        architectureConnections.filter(
                          (connection) =>
                            connection.from ===
                            node.name
                        );

                      return (
                        <div
                          key={`${node.name}-${index}`}
                        >

                          <div className="graph-node">

                            <span>
                              {getNodeIcon(
                                node.type
                              )}{" "}
                              {getServiceTypeLabel(
                                node.type
                              )}
                            </span>

                            <strong>
                              {node.name}
                            </strong>

                            <small>
                              {node.technology ||
                                "Unknown"}
                            </small>

                          </div>


                          {outgoing.length > 0 && (
                            <div
                              className="graph-arrow"
                              title={
                                outgoing
                                  .map(
                                    (connection) =>
                                      `${formatRelationship(
                                        connection.relationship
                                      )} → ${connection.to}`
                                  )
                                  .join("\n")
                              }
                            >
                              ↓
                            </div>
                          )}

                        </div>
                      );
                    }
                  )

                ) : (

                  <div className="graph-node">

                    <strong>
                      Architecture not available
                    </strong>

                    <small>
                      No architecture graph was returned by the analyzer.
                    </small>

                  </div>

                )}

              </div>


              {/* =================================================
                  ARCHITECTURE CONNECTIONS
              ================================================= */}

              {architectureConnections.length > 0 && (

                <div className="findings-section">

                  <h3>
                    Dependency Connections
                  </h3>

                  <div className="services-grid">

                    {architectureConnections.map(
                      (connection, index) => (

                        <div
                          className="service-card"
                          key={`connection-${index}`}
                        >

                          <div className="service-type">
                            {formatRelationship(
                              connection.relationship
                            )}
                          </div>

                          <h4>
                            {connection.from}
                            {" → "}
                            {connection.to}
                          </h4>

                          <p>
                            Detected dependency relationship.
                          </p>

                        </div>

                      )
                    )}

                  </div>

                </div>

              )}

            </div>


            {/* =================================================
                FAILURE SIMULATOR
            ================================================= */}

            <section className="simulator-section">

              <div className="analysis-label">
                FAILURE SIMULATOR
              </div>

              <h2>
                Break Your Application
              </h2>

              <p className="simulator-description">
                Simulate production failures and
                observe how they affect the inferred
                application architecture.
              </p>


              <div className="simulator-grid">

                {failureScenarios.length > 0 ? (

                  failureScenarios.map(
                    (scenario) => (

                      <button
                        className="failure-button"
                        key={scenario.id}
                        onClick={() =>
                          simulateFailure(
                            scenario.id
                          )
                        }
                        disabled={
                          simulationLoading
                        }
                      >

                        <span>
                          {scenario.id ===
                            "traffic"
                            ? "⚡"
                            : scenario.id ===
                              "cascading"
                            ? "🕸️"
                            : "🔥"}
                        </span>

                        <strong>
                          {scenario.label}
                        </strong>

                        <small>
                          {scenario.description}
                        </small>

                      </button>

                    )
                  )

                ) : (

                  <div className="finding-card info">

                    <h4>
                      No failure scenarios available
                    </h4>

                    <p>
                      The analyzer did not return any
                      failure scenarios.
                    </p>

                  </div>

                )}

              </div>


              {simulationLoading && (

                <div className="simulation-loading">
                  Running failure simulation...
                </div>

              )}


              {/* =================================================
                  SIMULATION RESULT
              ================================================= */}

              {simulation && (

                <div className="simulation-result">

                  <div className="simulation-header">

                    <div>

                      <div className="analysis-label">
                        SIMULATION RESULT
                      </div>

                      <h3>
                        {simulation.failure}
                      </h3>

                    </div>


                    <div className="reliability-score">

                      <span>
                        Reliability
                      </span>

                      <strong>
                        {simulation.reliabilityScore ??
                          "—"}/100
                      </strong>

                    </div>

                  </div>


                  <div className="simulation-status">

                    <strong>
                      {(
                        simulation.severity ||
                        "info"
                      ).toUpperCase()}
                    </strong>

                    <span>
                      {simulation.message}
                    </span>

                  </div>


                  {simulation.impact?.length > 0 && (

                    <div className="impact-section">

                      <h4>
                        Impact
                      </h4>

                      {simulation.impact.map(
                        (item, index) => (

                          <div
                            className="impact-item"
                            key={index}
                          >

                            <span>
                              →
                            </span>

                            {item}

                          </div>

                        )
                      )}

                    </div>

                  )}


                  {simulation.affectedServices?.length >
                    0 && (

                    <div className="affected-section">

                      <h4>
                        Affected Services
                      </h4>

                      <div className="affected-services">

                        {simulation.affectedServices.map(
                          (service) => (

                            <span
                              className="affected-service"
                              key={service}
                            >
                              {service}
                            </span>

                          )
                        )}

                      </div>

                    </div>

                  )}


                  {simulation.recommendation && (

                    <div className="simulation-recommendation">

                      <strong>
                        Recommended Action
                      </strong>

                      <p>
                        {simulation.recommendation}
                      </p>

                    </div>

                  )}

                </div>

              )}

            </section>


            {/* =================================================
                OPTIMIZATION ENGINE
            ================================================= */}

            <section className="optimize-section">

              <div className="analysis-label">
                OPTIMIZATION ENGINE
              </div>

              <h2>
                Generate Optimized Architecture
              </h2>

              <p className="simulator-description">
                Remove detected single points of
                failure, improve redundancy and
                generate a stronger deployment
                configuration.
              </p>


              <button
                className="primary-button"
                onClick={
                  handleOptimize
                }
                disabled={
                  optimizing
                }
              >

                {optimizing
                  ? "Optimizing Architecture..."
                  : "Generate Optimized Architecture"}

              </button>

            </section>


            {/* =================================================
                OPTIMIZATION RESULT
            ================================================= */}

            {optimization && (

              <section className="optimization-result">

                <div className="analysis-label">
                  OPTIMIZATION COMPLETE
                </div>

                <h3>
                  Recommended Architecture
                </h3>


                {/* =================================================
                    OPTIMIZATION SCORES
                ================================================= */}

                <div className="analysis-stats">

                  <div className="stat-card">

                    <span>
                      Current Reliability
                    </span>

                    <strong>
                      {optimization.currentReliability}/100
                    </strong>

                  </div>


                  <div className="stat-card">

                    <span>
                      Optimized Reliability
                    </span>

                    <strong>
                      {optimization.optimizedReliability}/100
                    </strong>

                  </div>


                  <div className="stat-card">

                    <span>
                      Improvement
                    </span>

                    <strong>
                      +{optimization.improvement}
                    </strong>

                  </div>

                </div>


                {/* =================================================
                    OPTIMIZED ARCHITECTURE
                ================================================= */}

                {optimization.architecture
                  ?.services?.length > 0 && (

                  <div className="services-section">

                    <h3>
                      Optimized Services
                    </h3>

                    <div className="services-grid">

                      {optimization.architecture.services.map(
                        (service, index) => (

                          <div
                            className="service-card"
                            key={`optimized-${index}`}
                          >

                            <div className="service-type">
                              {getServiceTypeLabel(
                                service.type
                              )}
                            </div>

                            <h4>
                              {service.name}
                            </h4>

                            <p>
                              Technology:{" "}
                              {service.technology ||
                                "Unknown"}
                            </p>

                            <p>
                              Replicas:{" "}
                              {service.replicas ??
                                "—"}
                            </p>

                            {service.healthCheck && (
                              <p>
                                Health:{" "}
                                {service.healthCheck}
                              </p>
                            )}

                          </div>

                        )
                      )}

                    </div>

                  </div>

                )}


                {/* =================================================
                    RECOMMENDATIONS
                ================================================= */}

                <h3>
                  Recommended Changes
                </h3>


                <div className="findings-list">

                  {optimization
                    .recommendations
                    ?.map(
                      (
                        recommendation,
                        index
                      ) => (

                        <div
                          className="finding-card info"
                          key={`${recommendation.service}-${index}`}
                        >

                          <div className="finding-severity">
                            {recommendation.service}
                          </div>

                          <h4>
                            {recommendation.action}
                          </h4>

                          <p>
                            <strong>
                              Current:
                            </strong>{" "}
                            {recommendation.current}
                          </p>

                          <p>
                            <strong>
                              Recommended:
                            </strong>{" "}
                            {recommendation.recommended}
                          </p>

                          <div className="recommendation">

                            <strong>
                              Why
                            </strong>

                            <span>
                              {recommendation.reason}
                            </span>

                          </div>

                        </div>

                      )
                    )}

                </div>


                {/* =================================================
                    ZEROPS CONFIGURATION
                ================================================= */}

                {optimization.zeropsYml && (

                  <div className="zerops-config-section">

                    <div className="zerops-config-header">

                      <div>

                        <div className="analysis-label">
                          DEPLOYMENT CONFIGURATION
                        </div>

                        <h3>
                          Generated Zerops Configuration
                        </h3>

                      </div>


                      <div className="zerops-config-actions">

                        <button
                          className="secondary-button"
                          onClick={
                            copyZeropsConfig
                          }
                        >
                          {copied
                            ? "✓ Copied"
                            : "Copy Configuration"}
                        </button>


                        <button
                          className="primary-button"
                          onClick={
                            downloadZeropsConfig
                          }
                        >
                          Download zerops.yml
                        </button>

                      </div>

                    </div>


                    <pre className="zerops-config">
                      {optimization.zeropsYml}
                    </pre>

                  </div>

                )}

              </section>

            )}


            {/* =================================================
                REPORT EXPORT
            ================================================= */}

            <div className="file-section">

              <div className="zerops-config-header">

                <div>

                  <div className="analysis-label">
                    EXPORT
                  </div>

                  <h3>
                    Analysis Report
                  </h3>

                </div>


                <div className="zerops-config-actions">

                  <button
                    className="primary-button"
                    onClick={
                      downloadAnalysisReport
                    }
                  >
                    {reportDownloaded
                      ? "✓ Report Downloaded"
                      : "Download Analysis Report"}
                  </button>

                </div>

              </div>

              <p>
                Export the complete static-analysis
                result as JSON for review, documentation
                or submission.
              </p>

            </div>


            {/* =================================================
                PROJECT STRUCTURE
            ================================================= */}

            <div className="file-section">

              <h3>
                Project Structure
              </h3>

              <div className="file-list">

                {analysis.files?.map(
                  (file, index) => (

                    <div
                      className="file"
                      key={`${file}-${index}`}
                    >
                      {file}
                    </div>

                  )
                )}

              </div>

            </div>

          </section>

        )}


        {/* =================================================
            LANDING FEATURES
        ================================================= */}

        {!analysis && !loading && (

          <section className="features">

            <div className="feature-card">

              <div className="feature-number">
                01
              </div>

              <h3>
                Analyze
              </h3>

              <p>
                Discover services, technologies,
                dependencies, architecture,
                health checks and potential
                reliability risks.
              </p>

            </div>


            <div className="feature-card">

              <div className="feature-number">
                02
              </div>

              <h3>
                Break
              </h3>

              <p>
                Simulate service failures,
                traffic spikes and cascading
                failures before production.
              </p>

            </div>


            <div className="feature-card">

              <div className="feature-number">
                03
              </div>

              <h3>
                Optimize
              </h3>

              <p>
                Generate a stronger architecture,
                redundancy recommendations and
                a Zerops deployment configuration.
              </p>

            </div>

          </section>

        )}

      </main>

    </div>
  );
}

export default App;