FROM python:3.11-slim
WORKDIR /app
# Optional deps for live mode; demo mode needs none of these.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true
COPY backend/ ./backend/
COPY frontend/ ./frontend/
ENV DB_PATH=/data/adsathi.db PORT=8000
VOLUME ["/data"]
EXPOSE 8000
WORKDIR /app/backend
CMD ["python3", "-m", "app.main"]
