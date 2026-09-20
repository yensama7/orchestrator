# Build the static SPA, then serve it with nginx (which also reverse-proxies
# /api → backend). Production: no dev server, no source in the runtime image.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# API_UPSTREAM is templated into the vhost at start (nginx image runs
# envsubst over /etc/nginx/templates/*.template on boot).
ENV API_UPSTREAM=http://backend:8000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 5173
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -qO- http://127.0.0.1:5173/ >/dev/null || exit 1
