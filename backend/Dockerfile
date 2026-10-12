FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lineage ./lineage
# Run as a non-root user — nothing here needs root at runtime. ~/.lineage holds
# the auto-generated secret-at-rest key (vault.py); create it owned by app so the
# named volume compose mounts there initialises writable for uid 10001.
RUN useradd --create-home --uid 10001 app && chown -R app /app \
 && install -d -o app -g app /home/app/.lineage
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"
CMD ["uvicorn", "lineage.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
