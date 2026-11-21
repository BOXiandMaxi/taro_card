FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/app/backend
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY database/ /app/database/
COPY --from=frontend /build/frontend/dist/ /app/frontend/dist/
WORKDIR /app/backend
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app.render_web:app --host 0.0.0.0 --port ${PORT:-10000}"]
