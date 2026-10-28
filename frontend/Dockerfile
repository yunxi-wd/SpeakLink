# Build the web client and preserve the backend URL in its Next.js proxy.
FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
COPY frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
ENV API_URL=http://backend:8000
ENV NEXT_TELEMETRY_DISABLED=1
ENV KNOWGPT_STANDALONE=1
RUN pnpm build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
