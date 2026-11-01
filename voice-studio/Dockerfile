FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/gustava-voice
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core.py app.py index.html site.css site.js ./
RUN useradd --uid 10001 --create-home --no-log-init voiceapp \
    && mkdir -p /data/audio \
    && chown -R voiceapp:voiceapp /data /opt/gustava-voice
USER voiceapp
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-server-header"]
