# --- Build stage -----------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
# VITE_API_URL is baked into the static bundle at build time; override via
# --build-arg when pointing at a non-default backend URL.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- Serve stage -------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS serve
COPY --from=build /app/dist /usr/share/nginx/html
# SPA fallback: any unknown path resolves to index.html so React Router can
# handle client-side routes like /records/:id/media.
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
