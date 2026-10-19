FROM python:3.12.8-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    useradd -r -u 10001 -m -s /usr/sbin/nologin onionrelay && \
    chown -R onionrelay:onionrelay /app
COPY --chown=onionrelay:onionrelay relay.py .
USER onionrelay
EXPOSE 8080
CMD ["gunicorn", "-w", "1", "--threads", "16", "-b", "0.0.0.0:8080", "relay:app"]

