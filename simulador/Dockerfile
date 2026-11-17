# Build a partir da raiz do repositório:
#   docker build -f simulador/Dockerfile -t simple-ihm-simulador .
FROM python:3.13-slim
WORKDIR /app
COPY simulador/requirements.txt simulador/requirements.txt
RUN pip install --no-cache-dir -r simulador/requirements.txt
COPY simulador/ simulador/
ENV PORT=8081
EXPOSE 8081
CMD ["python", "-m", "simulador.main"]
