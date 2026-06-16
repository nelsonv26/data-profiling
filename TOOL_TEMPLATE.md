# TOOL_TEMPLATE — Adding a New Tool to adoreal-tools

Follow this guide every time a new automation tool is added to the platform.
Target: from zero to deployed in under 2 hours.

---

## 1. Folder structure

Create a top-level folder for your tool. Use lowercase and hyphens:

```
adoreal-tools/
└── your-tool-name/
    ├── app.py              # or main.py, index.ts — your entry point
    ├── requirements.txt    # or package.json
    ├── Dockerfile          # see Section 2
    ├── .dockerignore       # see Section 2
    └── README.md           # see Section 5
```

**Rule:** one folder = one tool = one Dockerfile = one Helm chart.
Never put two tools in the same folder.

---

## 2. Dockerfile

Choose the template that matches your stack and copy it into `your-tool-name/Dockerfile`.

### Streamlit (Python)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none", \
     "--server.baseUrlPath=/your-tool-name"]
```

> ⚠️ Replace `/your-tool-name` with the actual path prefix (must match Section 4).

### FastAPI / Flask (Python)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Next.js (Node)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

### .dockerignore (put one in every tool folder)

```
__pycache__/
*.pyc
.venv/
venv/
.env
*.env
node_modules/
.next/
*.log
```

---

## 3. Helm chart

Copy the dataprofile chart as a starting point:

```bash
cp -r charts/dataprofile charts/your-tool-name
```

Then edit these two files:

### `charts/your-tool-name/Chart.yaml`

```yaml
apiVersion: v2
name: your-tool-name
description: One-line description of what this tool does
type: application
version: 0.1.0
appVersion: "1.0.0"
```

### `charts/your-tool-name/values.yaml`

```yaml
replicaCount: 1

namespace: tools-prod

image:
  repository: your-tool-name
  tag: latest
  pullPolicy: Never          # Never for local; Always for remote registry

service:
  type: ClusterIP
  port: 8501                 # Change to 8000 (FastAPI) or 3000 (Next.js)

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

# Add any environment variables your tool needs:
env: {}
# env:
#   MY_VAR: "value"
```

### `charts/your-tool-name/values-prod.yaml` (gitignored — never commit secrets)

```yaml
image:
  repository: <registry-url>/your-tool-name
  pullPolicy: Always

env:
  MY_SECRET_VAR: "real-value"
```

> Add `charts/*/values-prod.yaml` to `.gitignore` if not already there.

---

## 4. Register the tool in the Ingress

Open `k8s/ingress.yaml` and add a path block **before** the portal catch-all (`/`):

```yaml
- path: /your-tool-name(/|$)(.*)
  pathType: Prefix
  backend:
    service:
      name: your-tool-name
      port:
        number: 8501          # must match service.port in values.yaml
```

---

## 5. Add a card to the portal

Open `portal/src/app/page.tsx` and add an entry to the tools list:

```typescript
{
  name: "Your Tool Name",
  description: "One sentence describing what it does and who it's for.",
  path: "/your-tool-name/",
  icon: "🔧",                  // pick a relevant emoji
  status: "live",              // "live" | "beta" | "coming-soon"
}
```

---

## 6. README.md for your tool

Create `your-tool-name/README.md` using this template:

```markdown
# Your Tool Name

One-paragraph description: what it does, who uses it, and why.

---

## Requirements

- Python 3.11+ / Node 20+
- (list any external services or credentials needed)

---

## Run locally

```bash
cd your-tool-name
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
streamlit run app.py
```

App opens at http://localhost:8501

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| MY_VAR   | Yes      | What it does |

---

## Deploy to local Kubernetes

```powershell
# From repo root:
.\scripts\deploy.ps1 -AppName your-tool-name
```

## Stop

```powershell
.\scripts\stop.ps1 -AppName your-tool-name
```

---

## Health check endpoint

`GET /_stcore/health` (Streamlit) / `GET /health` (FastAPI) / `GET /api/health` (Next.js)
```

---

## 7. Deploy locally

```powershell
# From repo root — builds image, loads into k8s, deploys with Helm, opens port-forward
.\scripts\deploy.ps1 -AppName your-tool-name

# Override port if needed (e.g. FastAPI on 8000):
.\scripts\deploy.ps1 -AppName your-tool-name -Port 8000

# Deploy to dev namespace:
.\scripts\deploy.ps1 -AppName your-tool-name -Namespace tools-dev
```

---

## 8. Stop / teardown

```powershell
# Remove just this tool (namespace kept — other tools still running):
.\scripts\stop.ps1 -AppName your-tool-name

# Remove tool AND delete the namespace (careful if other tools are in it):
.\scripts\stop.ps1 -AppName your-tool-name -DeleteNamespace
```

---

## 9. Checklist before opening a PR

- [ ] `your-tool-name/Dockerfile` builds without errors (`docker build -t your-tool-name .`)
- [ ] App runs locally with `docker run -p PORT:PORT your-tool-name`
- [ ] `charts/your-tool-name/` created and `helm lint charts/your-tool-name` passes
- [ ] Path added to `k8s/ingress.yaml`
- [ ] Card added to `portal/src/app/page.tsx`
- [ ] `your-tool-name/README.md` written with env vars documented
- [ ] `values-prod.yaml` added to `.gitignore` (no secrets in git)
- [ ] `.\scripts\deploy.ps1 -AppName your-tool-name` runs end-to-end without errors