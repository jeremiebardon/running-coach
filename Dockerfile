# syntax=docker/dockerfile:1

# ---- deps: production dependencies only (tsx is a runtime dep for this POC) ----
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ---- runtime ----
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production PORT=3000

COPY --from=deps /app/node_modules ./node_modules
COPY package.json tsconfig.json ./
COPY src ./src
COPY fixtures ./fixtures

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

# node is PID 1 and handles SIGTERM itself (graceful shutdown + span flush in main.ts)
CMD ["node", "--import", "tsx", "src/server/main.ts"]
