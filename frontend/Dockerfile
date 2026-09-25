# --- build stage ---
FROM node:20-alpine AS build
WORKDIR /srv

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Where the browser finds the API. Override at build time:
#   docker build --build-arg VITE_API_URL=https://api.example.com .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# --- serve stage ---
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /srv/dist /usr/share/nginx/html

EXPOSE 80
