# api-propuesta-sfv/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema si fueran necesarias
# RUN apt-get update && apt-get install -y ...

# Copiar requirements e instalar librerías
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn uvicorn

# Copiar el resto del código
COPY . .

# Exponer el puerto
EXPOSE 8000

# Comando de arranque
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]