# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Production server
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY server.js .
COPY --from=build /app/dist ./dist

EXPOSE 8080

# API_URL is set at runtime (Railway private networking)
# e.g. API_URL=http://backend.railway.internal:8000
CMD ["node", "server.js"]
