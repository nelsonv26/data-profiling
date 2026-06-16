# Adoreal Automation Tools

Internal tooling platform for Adoreal's clinical operations and data engineering workflows.
All tools are deployed to a shared Kubernetes cluster and accessible from a single internal URL.

---

## Tools

| Folder | Tool | Stack | Path | Status |
|--------|------|-------|------|--------|
| `dataprofile/` | Data Profiling Tool | Streamlit / Python | `/dataprofile/` | ✅ Live (local) |
| `portal/` | Automation Portal | Next.js | `/` | 🔧 In development |

> To add a new tool, follow **[TOOL_TEMPLATE.md](./TOOL_TEMPLATE.md)**.

---

## Repository structure

```
adoreal-tools/
├── .github/
│   └── workflows/
│       ├── ci.yml                   # build + helm lint on every PR
│       └── deploy-{app}.yml         # per-tool deploy on push to main
│
├── charts/                          # Helm charts — one per tool
│   ├── _common/                     # shared helpers
│   ├── portal/
│   └── dataprofile/
│
├── k8s/                             # shared Kubernetes manifests
│   ├── namespace.yaml
│   └── ingress.yaml                 # Nginx Ingress — routes all tools
│
├── scripts/                         # operational scripts
│   ├── deploy.ps1                   # build + deploy any tool locally
│   └── stop.ps1                     # teardown any tool locally
│
├── portal/                          # Next.js portal (tool launcher)
├── dataprofile/                     # Data Profiling Tool
├── {your-tool}/                     # future tools follow the same pattern
│
├── TOOL_TEMPLATE.md                 # guide for adding new tools
└── README.md
```

---

## Running a tool locally (Kubernetes)

```powershell
# Deploy any tool — replace 'dataprofile' with the tool folder name
.\scripts\deploy.ps1 -AppName dataprofile

# Stop a tool (keeps namespace and other tools running)
.\scripts\stop.ps1 -AppName dataprofile

# Stop + delete namespace (use only if no other tools are running in it)
.\scripts\stop.ps1 -AppName dataprofile -DeleteNamespace
```

The script auto-detects the port from `charts/{AppName}/values.yaml`.
Override it with `-Port 8000` if needed.

---

## Kubernetes architecture

```
Browser
  │
  ▼
Ingress (nginx)  ──►  /                  →  portal        (port 3000)
                 ──►  /dataprofile/      →  dataprofile   (port 8501)
                 ──►  /{tool-name}/      →  {tool-name}   (port varies)

Namespace: tools-prod (production)
           tools-dev  (dev / staging)
```

All tools share a single namespace per environment.
Each tool has its own Deployment, Service, and Helm chart.

---

## Deploying to the Adoreal cluster (production)

```powershell
# 1. Tag and push image to registry (ask infra for the URL)
docker tag dataprofile:latest <registry-url>/dataprofile:latest
docker push <registry-url>/dataprofile:latest

# 2. Switch context
kubectl config use-context kubernetes-admin@kubernetes

# 3. Deploy with production values
helm upgrade --install dataprofile charts/dataprofile `
  --namespace tools-prod `
  --create-namespace `
  -f charts/dataprofile/values-prod.yaml
```

---

## Adding a new tool

See **[TOOL_TEMPLATE.md](./TOOL_TEMPLATE.md)** for the full step-by-step guide.
Quick checklist:

1. Create `your-tool/` folder with code + `Dockerfile`
2. Copy `charts/dataprofile/` → `charts/your-tool/` and update `Chart.yaml` + `values.yaml`
3. Add a path entry to `k8s/ingress.yaml`
4. Add a card to `portal/src/app/page.tsx`
5. Run `.\scripts\deploy.ps1 -AppName your-tool` and verify end-to-end

---

## Documentation

- [PRD](https://adoreal.atlassian.net/wiki/spaces/Automation/pages/516358148) — Product Requirements Document
- [TRD](https://adoreal.atlassian.net/wiki/spaces/Automation/pages/516358168) — Technical Requirements Document
- [Jira board](https://adoreal.atlassian.net/jira/software/projects/AUTO/boards/34/backlog) — AUTO project backlog