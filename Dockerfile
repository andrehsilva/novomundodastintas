



# Passo 1: Imagem Base
FROM python:3.11-slim-bookworm

# Passo 2: Variáveis de Ambiente
ENV PYTHONUNBUFFERED=1
# Porta padrão para o EasyPanel ou Railway
ENV PORT=8080

# Passo 3: Diretório de Trabalho dentro do Container
WORKDIR /app

# Passo 4: Instalar Dependências do Sistema (Necessário para pacotes Python complexos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Passo 5: Instalar Dependências do Python
# Primeiro copiamos apenas o requirements para aproveitar o cache do Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Passo 6: CORREÇÃO DA ESTRUTURA DE PASTAS
# De acordo com seu explorer, seus arquivos estão na raiz do projeto.
# Copiamos tudo da sua raiz para a raiz /app do container.
COPY . .

# Passo 7: Criar pastas necessárias e ajustar permissões
# Criamos a pasta de uploads dentro de static caso ela não exista no git
RUN mkdir -p /app/static/uploads /app/instance && chmod -R 777 /app/static/uploads /app/instance

# Passo 8: Expor a Porta
EXPOSE $PORT

# Passo 9: Comando de Execução
# Ajustado para usar o Gunicorn chamando diretamente o objeto 'app' do seu arquivo 'app.py'
CMD gunicorn --bind 0.0.0.0:$PORT app:app