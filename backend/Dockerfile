FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# --workers 1 is deliberate, not the default omitted: sessions live in this
# process's memory (per-session DuckDB connection + lock, see Phase 6), so
# a second worker process would have its own disjoint copy of every
# session and requests could land on either one.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
