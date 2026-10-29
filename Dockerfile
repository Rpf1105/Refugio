# Refúgio — protótipo empacotado como um único Container Docker (R13).
# Base enxuta com Python 3.12.
FROM python:3.12-slim

# Comportamento previsível em container:
# - não gera arquivos .pyc
# - não faz buffer de stdout/stderr (logs aparecem na hora)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala as dependências primeiro para aproveitar o cache de camadas:
# a camada de dependências só é refeita quando requirements.txt muda.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação (pacote app/).
COPY app ./app

# Banco SQLite (/data/refugio.db) e fotos (/data/fotos) persistem no volume.
VOLUME ["/data"]

# Porta exposta pela Interface Web (Uvicorn).
EXPOSE 8000

# Sobe a aplicação FastAPI via Uvicorn, acessível fora do container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
