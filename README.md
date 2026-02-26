# Clube Novo Mundo - Programa de Fidelidade

Aplicação Flask para gestão de saldo de pontos, catálogo de prêmios, extrato e operações administrativas.

## Funcionalidades

- Dashboard com saldo total em destaque
- Catálogo de prêmios com cards
- Extrato cronológico de transações
- Painel administrativo para:
  - crédito manual de pontos
  - upload de CSV para crédito em lote

## Modelo de dados

- `User`: nome, email, CPF/CNPJ, senha (hash), saldo total
- `Product`: nome, descrição, valor em pontos, imagem, categoria
- `Transaction`: usuário, pontos (+/-), data, descrição

## Executar localmente

> Requer Python 3.10+

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Aplicação disponível em `http://127.0.0.1:5000`.

## CSV do painel administrativo

Use um arquivo com cabeçalho:

```csv
pontos,descricao
150,Compra NF 12345
250,Compra NF 12346
```

- `pontos`: inteiro (positivo para crédito, negativo para débito)
- `descricao`: texto opcional
