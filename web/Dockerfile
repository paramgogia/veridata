# Argus frontend (Next.js). NEXT_PUBLIC_* values are baked in at build time: pass them as build args
# (Railway passes service variables to ARGs automatically).
FROM node:20-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ARKIV_ACCESS_KEY=""
ARG NEXT_PUBLIC_SEPOLIA_RPC=""
ARG NEXT_PUBLIC_WHITECHAIN_RPC=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_ARKIV_ACCESS_KEY=$NEXT_PUBLIC_ARKIV_ACCESS_KEY \
    NEXT_PUBLIC_SEPOLIA_RPC=$NEXT_PUBLIC_SEPOLIA_RPC \
    NEXT_PUBLIC_WHITECHAIN_RPC=$NEXT_PUBLIC_WHITECHAIN_RPC
RUN test -n "$NEXT_PUBLIC_API_URL" || (echo "NEXT_PUBLIC_API_URL must be set (the backend's public URL)" && exit 1)
RUN npm run build && npm prune --omit=dev

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
COPY --from=build /app/package.json /app/next.config.mjs ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
EXPOSE 3000
CMD ["sh", "-c", "npx next start -p ${PORT:-3000}"]
