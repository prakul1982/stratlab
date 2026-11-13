# The site on Railway: the app built with Node, served by Caddy (see Caddyfile). Images from Docker Hub, packages from npm only.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# keepAssets carries the last builds' page code from the live site (a tab opened before a deploy keeps working); it never fails a build
RUN npm run build && KEEP_ASSETS_FROM=${KEEP_ASSETS_FROM:-https://stratlab.studio} node scripts/keepAssets.mjs

FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
