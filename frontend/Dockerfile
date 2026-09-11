# Nightwire web frontend (Next.js standalone). Build context = frontend/.
FROM node:22-slim AS deps
WORKDIR /app
# better-sqlite3 compiles a native binding at install time.
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN useradd --create-home --uid 10001 nightwire
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nightwire:nightwire /app/.next/standalone ./
COPY --from=builder --chown=nightwire:nightwire /app/.next/static ./.next/static

USER nightwire
EXPOSE 3000
CMD ["node", "server.js"]
