# 🚀 Zerops Autopilot

> **Break your application before production does.**

Zerops Autopilot is an AI-native reliability and deployment analysis engine that analyzes an application's architecture, discovers services and dependencies, identifies reliability risks and potential bottlenecks, simulates production failures, and generates a more resilient Zerops deployment configuration.

The goal is simple:

**Find weaknesses before production finds them.**

---

## 🎯 The Problem

Modern applications are rarely a single service.

A typical application may contain:

- Frontend services
- Backend APIs
- Background workers
- Databases
- Message queues
- Caches
- Object storage
- Containers
- External dependencies

As applications become more distributed, reliability problems become harder to identify.

A deployment can look completely healthy while still containing:

- Single points of failure
- Missing redundancy
- Missing health checks
- Worker reliability problems
- Missing queue infrastructure
- Potential bottlenecks
- Missing CI/CD
- Missing Infrastructure-as-Code
- Weak deployment configurations

Developers usually discover these problems **after deployment**.

Zerops Autopilot takes a different approach.

Instead of waiting for production to fail, it analyzes the application first.

---

# 💡 What Zerops Autopilot Does

Zerops Autopilot follows a simple pipeline:

```text
                    ┌─────────────────────┐
                    │   Upload Project    │
                    │       .zip          │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Static Analysis   │
                    │                     │
                    │ Services            │
                    │ Technologies        │
                    │ Dependencies        │
                    │ Deployment Signals  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Reliability Engine  │
                    │                     │
                    │ SPOFs               │
                    │ Redundancy          │
                    │ Queues              │
                    │ Health Checks       │
                    │ CI/CD               │
                    │ IaC                 │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
       ┌─────────────────┐           ┌─────────────────┐
       │ Failure         │           │ Bottleneck      │
       │ Simulator       │           │ Analysis        │
       └────────┬────────┘           └────────┬────────┘
                │                             │
                └──────────────┬──────────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Optimization Engine │
                    │                     │
                    │ Scale services      │
                    │ Add redundancy       │
                    │ Add health checks    │
                    │ Improve resilience   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Zerops Configuration│
                    │     Generation      │
                    └─────────────────────┘
```

---

# ✨ Core Features

## 1. 📦 Project Analysis

Upload a project as a ZIP archive.

Zerops Autopilot extracts and analyzes the project without requiring a database or external AI API for its core static analysis.

The analyzer can detect:

- Project files
- Technologies
- Application services
- Service types
- Dependencies
- Ports
- Health endpoints
- Container configuration
- Existing Zerops configuration
- CI/CD configuration
- Infrastructure-as-Code signals

---

# 2. 🔍 Technology Detection

The analyzer identifies technologies used by the project.

Example:

```text
Node.js / JavaScript
Python
Docker / OCI
```

Technology detection is based on project structure and configuration files.

---

# 3. 🧩 Service Detection

Application services are identified from the uploaded project.

For example:

```text
BACKEND
api
Node.js / Express

WORKER
worker
Python / Flask

FRONTEND
frontend
Node.js / React + Vite
```

Each detected service can include:

- Service name
- Service type
- Technology
- Directory
- Health endpoint
- Deployment signals

---

# 4. 🔗 Dependency Analysis

Zerops Autopilot builds an inferred dependency graph.

For example:

```text
FRONTEND
   │
   │ Request
   ▼
BACKEND
   │
   │ Processing
   ▼
WORKER
```

The system identifies relationships such as:

```text
frontend → api
api → worker
```

These relationships are then used by the reliability and failure simulation engines.

---

# 5. 🗄️ Infrastructure Dependency Detection

The analyzer checks for infrastructure dependencies such as:

### Databases

```text
MongoDB
PostgreSQL
MySQL
Redis
SQLite
```

### Message Queues

```text
RabbitMQ
Kafka
Redis queues
Celery
Bull/BullMQ
SQS
```

### Caches

Cache infrastructure can be detected from project configuration and dependencies.

### Object Storage

The analyzer can identify object-storage related infrastructure signals.

The dashboard summarizes these dependencies so developers can understand the application's infrastructure requirements.

---

# 6. 🚨 Reliability Analysis

The reliability engine looks for common architectural weaknesses.

Examples include:

### Single Point of Failure

```text
🔴 CRITICAL

api Single Point of Failure

Only one instance is statically represented for api.

Recommendation:
Run at least 2 api instances behind a
health-aware load balancer.
```

### Missing Worker Redundancy

```text
🟠 WARNING

Worker Redundancy Not Detected

Recommendation:
Run multiple workers and use durable
queue semantics where applicable.
```

### Missing Frontend Redundancy

```text
🟠 WARNING

Frontend Redundancy Not Detected
```

### Missing Queue Infrastructure

```text
🟠 WARNING

Worker Queue Not Detected
```

### Missing CI/CD

```text
🔵 INFO

CI/CD Configuration Not Detected
```

### Missing Infrastructure-as-Code

```text
🔵 INFO

Infrastructure-as-Code Not Detected
```

Each finding contains:

- Severity
- Title
- Description
- Recommendation

---

# 7. 📊 Reliability Score

The application receives a reliability score based on the detected architecture and reliability findings.

Example:

```text
Current Reliability

44 / 100
```

After optimization:

```text
Optimized Reliability

100 / 100
```

The dashboard also shows the improvement:

```text
Improvement

+56
```

The score is intended as an architectural assessment rather than a guarantee of real-world availability.

---

# 8. ⚡ Bottleneck Analysis

Zerops Autopilot also analyzes potential performance and capacity bottlenecks.

The dashboard highlights potential bottlenecks and explains that they may originate from:

- Service capacity
- Dependencies
- Worker architecture
- Missing infrastructure components
- Traffic handling

This allows developers to investigate possible performance limitations before production.

---

# 9. 🏗️ Deployment Analysis

The analyzer checks deployment-related signals.

Examples include:

### Ports

```text
PORTS

9000
```

### Health endpoints

```text
HEALTH ENDPOINTS

/health
```

### Containers

```text
CONTAINERS

frontend/Dockerfile
```

### Zerops configuration

```text
ZEROPS

Detected / Not detected
```

This provides a quick overview of the project's deployment readiness.

---

# 10. 🧪 Failure Simulator

One of the core features of Zerops Autopilot is the failure simulator.

Instead of only identifying risks, the application allows developers to simulate failures against the inferred architecture.

Available scenarios include:

### 🔥 API Failure

Simulates failure of the backend service.

### 🔥 Worker Failure

Simulates failure of the worker service.

### 🔥 Frontend Failure

Simulates failure of the frontend service.

### ⚡ Traffic Spike ×10

Simulates a tenfold increase in incoming traffic.

### 🕸️ Cascading Failure

Simulates failure propagation through the inferred dependency graph.

---

# 11. 🧠 Cascading Failure Analysis

Distributed systems can fail through dependency chains.

For example:

```text
Frontend
   │
   ▼
API
   │
   ▼
Worker
```

If the API fails, the frontend may no longer be able to serve requests.

If the worker fails, background processing may be interrupted.

Zerops Autopilot uses the inferred dependency graph to estimate how failures can propagate through the application.

---

# 12. 🔧 Optimization Engine

After analyzing an application, the user can generate an optimized architecture.

Example:

```text
CURRENT

api       → 1 instance
worker    → 1 instance
frontend  → 1 instance


OPTIMIZED

api       → 2 instances
worker    → 2 instances
frontend  → 2 instances
```

The optimizer generates recommendations such as:

```text
Scale horizontally
Enable worker redundancy
Enable frontend redundancy
Add health checks
Review queue architecture
```

Each recommendation explains:

- Service
- Action
- Current state
- Recommended state
- Reason

---

# 13. 🚀 Zerops Configuration Generation

After optimization, Zerops Autopilot generates a deployment configuration.

Example:

```yaml
# Generated by Zerops Autopilot

# Review service names, build commands and health-check ports before deployment.

zerops:

- setup: api
  run:
  base: nodejs@latest
  start: npm start

- setup: worker
  run:
  base: python@latest
  start: python main.py

- setup: frontend
  run:
  base: nodejs@latest
  start: npm start
```

The configuration is generated from the analyzed project architecture and optimization recommendations.

Users can:

- View the generated configuration
- Copy the configuration
- Download `zerops.yml`

> **Important:** Generated deployment configuration should always be reviewed against the actual project's service names, build commands, ports, health endpoints, and Zerops deployment requirements before production deployment.

---

# 14. 📄 Analysis Report

The application can export the analysis result as JSON.

The report can be used for:

- Architecture review
- Documentation
- Debugging
- Competition demonstration
- Deployment planning
- Reliability review

The report contains the information generated by the analysis engine.

---

# 🖥️ Dashboard

The web interface provides a complete visualization of the analysis.

The dashboard includes:

```text
Analysis Complete
        │
        ├── Project Statistics
        ├── Technologies
        ├── Services
        ├── Dependencies
        ├── Deployment Analysis
        ├── Reliability Analysis
        ├── Bottleneck Analysis
        ├── Delivery Readiness
        ├── Architecture Map
        ├── Failure Simulator
        ├── Optimization Engine
        ├── Zerops Configuration
        └── Project Structure
```

---

# 🏛️ Architecture

Zerops Autopilot is divided into three primary components.

```text
┌──────────────────────────┐
│        FRONTEND          │
│                          │
│ React + Vite             │
│ Dashboard / UI           │
└────────────┬─────────────┘
             │
             │ HTTP API
             ▼
┌──────────────────────────┐
│         BACKEND          │
│                          │
│ Node.js + Express        │
│                          │
│ Upload handling          │
│ API routing              │
│ Analyzer communication   │
│ Simulation               │
│ Optimization             │
└────────────┬─────────────┘
             │
             │ HTTP
             ▼
┌──────────────────────────┐
│        ANALYZER          │
│                          │
│ Python + Flask           │
│                          │
│ Static analysis          │
│ Technology detection     │
│ Dependency detection     │
│ Reliability analysis     │
│ Bottleneck analysis      │
│ Failure simulation       │
│ Optimization             │
└──────────────────────────┘
```

---

# 📁 Project Structure

```text
zerops/
│
├── README.md
│
├── analyzer/
│   ├── app.py
│   └── requirements.txt
│
├── backend/
│   ├── server.js
│   └── package.json
│
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   └── App.css
    │
    └── package.json
```

---

# 🧰 Technology Stack

## Frontend

- React
- Vite
- JavaScript
- CSS

## Backend

- Node.js
- Express
- Multer
- Axios
- CORS
- FormData

## Analyzer

- Python
- Flask
- ZIP processing
- Regular expressions
- JSON processing
- Static project analysis

---

# 🔄 Complete Workflow

A typical analysis looks like this:

### Step 1 — Upload

The developer uploads:

```text
my-project.zip
```

### Step 2 — Backend receives the project

The Node.js backend handles the upload and communicates with the analyzer.

### Step 3 — Analyzer extracts the project

The Python analyzer examines the project structure and configuration files.

### Step 4 — Technologies are detected

For example:

```text
Node.js
Python
Docker
React
```

### Step 5 — Services are identified

For example:

```text
frontend
api
worker
```

### Step 6 — Dependencies are inferred

```text
frontend → api
api → worker
```

### Step 7 — Reliability is evaluated

Potential risks are generated.

```text
Critical: 1
Warnings: 3
Information: 2
```

### Step 8 — Failure scenarios are simulated

The user can test:

```text
API failure
Worker failure
Frontend failure
Traffic spike
Cascading failure
```

### Step 9 — Architecture is optimized

The optimizer recommends changes.

```text
api       → 2 instances
worker    → 2 instances
frontend  → 2 instances
```

### Step 10 — Deployment configuration is generated

A Zerops deployment configuration is produced.

---

# 🧪 Example Analysis

For a project containing:

```text
README.md
api/index.js
api/package.json
worker/main.py
worker/requirements.txt
frontend/package.json
frontend/Dockerfile
```

Zerops Autopilot can infer:

```text
BACKEND
api
Node.js / Express

WORKER
worker
Python / Flask

FRONTEND
frontend
Node.js / React + Vite
```

Architecture:

```text
frontend
   │
   │ Request
   ▼
api
   │
   │ Processing
   ▼
worker
```

Potential reliability result:

```text
Current Reliability: 44/100
```

After optimization:

```text
Optimized Reliability: 100/100
Improvement: +56
```

The optimizer may recommend:

```text
api
2+ instances

worker
2+ instances

frontend
2+ instances

worker infrastructure
Durable message queue
```

---

# 🚀 Running Locally

## Prerequisites

Install:

- Node.js
- npm
- Python 3
- pip

---

## 1. Start the Analyzer

Open a terminal:

```bash
cd analyzer
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start Flask:

```bash
python app.py
```

The analyzer runs on:

```text
http://127.0.0.1:5000
```

---

# 2. Start the Backend

Open another terminal:

```bash
cd backend
```

Install dependencies:

```bash
npm install
```

Start the server:

```bash
npm start
```

The backend runs on:

```text
http://localhost:3000
```

---

# 3. Start the Frontend

Open another terminal:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start Vite:

```bash
npm run dev
```

Open the URL shown by Vite, typically:

```text
http://localhost:5173
```

---

# 🔌 API Overview

The backend exposes endpoints used by the frontend.

## Upload

```http
POST /api/upload
```

Uploads a project ZIP and starts the analysis process.

---

## Failure Simulation

```http
POST /api/simulate
```

Runs a failure scenario against the analyzed architecture.

Example request:

```json
{
  "failure": "api",
  "analysis": {}
}
```

---

## Optimization

```http
POST /api/optimize
```

Generates optimization recommendations and deployment configuration.

Example request:

```json
{
  "analysis": {}
}
```

---

# 🔐 Design Philosophy

Zerops Autopilot is designed around several principles.

## Analyze before deploying

Don't wait for production failures to reveal architectural problems.

## Explain every recommendation

The system doesn't only say:

```text
Add redundancy
```

It explains:

```text
Why redundancy is required
Current architecture
Recommended architecture
```

## Failure-aware architecture

Reliability isn't just about detecting configuration problems.

The system also models what can happen when services fail.

## Deployment-aware recommendations

The optimization engine connects architecture analysis with deployment configuration.

---

# 🧠 Static Analysis Instead of External AI APIs

The current analyzer is designed to operate through static project analysis.

It does not require an external AI API to perform its core analysis.

This makes the system:

- Self-contained
- Reproducible
- Easier to demonstrate
- Less dependent on external API availability
- Suitable for analyzing uploaded project structures

The "AI-native" aspect refers to the architecture and automation goal of the product; the current implementation's core analysis is deterministic/static rather than dependent on a third-party LLM.

---

# ⚠️ Important Limitations

Zerops Autopilot performs **static architectural analysis**.

Therefore, its results should be treated as engineering recommendations rather than guarantees.

Static analysis cannot perfectly determine:

- Actual runtime traffic
- Real CPU utilization
- Memory pressure
- Network latency
- Production request patterns
- Actual database load
- Real-world failure rates
- Application-specific business logic

Similarly, generated deployment configurations should be reviewed before production use.

---

# 🔮 Future Improvements

Potential future extensions include:

- Runtime telemetry analysis
- Real production metrics
- CPU and memory profiling
- Load testing
- Automatic deployment validation
- Real Zerops deployment integration
- Runtime dependency discovery
- More advanced bottleneck detection
- Queue topology analysis
- Database availability analysis
- Automated rollback recommendations
- Predictive failure analysis
- LLM-assisted architecture explanations

---

# 🏆 Competition Demo Flow

For a strong demonstration, use this sequence:

```text
1. Upload a sample application
          ↓
2. Show detected services
          ↓
3. Show dependency graph
          ↓
4. Show reliability score
          ↓
5. Show critical risk
          ↓
6. Run API Failure
          ↓
7. Show affected services
          ↓
8. Run Cascading Failure
          ↓
9. Generate optimized architecture
          ↓
10. Show reliability improvement
          ↓
11. Show optimized services
          ↓
12. Generate Zerops configuration
          ↓
13. Download / review configuration
```

This demonstrates the entire product concept rather than only showing a dashboard.

---

# 📜 License

This project was created as part of the Zerops Challenge.

---

# 🚀 Zerops Autopilot

**Analyze your architecture.**

**Break your application.**

**Understand the failure.**

**Optimize the deployment.**

**Deploy with confidence.**

> **Break your application before production does.**
