# Forza Live server: docker build -t forza-live server/ &&
#   docker run --network host -v forza-live-data:/data forza-live --http-port 21201
# (or -p 21200:21200/udp -p 21201:21201; --network host keeps players' public ports intact)
FROM python:3.12-slim
WORKDIR /app
COPY *.py *.xml ./
EXPOSE 21200/udp 21201/tcp
VOLUME /data
ENTRYPOINT ["python3", "forza_live_server.py", "--port", "21200", "--http-port", "21201", "--data-dir", "/data"]
