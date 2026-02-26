from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    cpf_cnpj = db.Column(db.String(20), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    saldo_total = db.Column(db.Integer, nullable=False, default=0)
    
    # Define se é 'admin' ou 'pintor'
    role = db.Column(db.String(20), nullable=False, default='pintor') 
    # Controle de acesso para novos cadastros
    ativo = db.Column(db.Boolean, default=False) 

    transacoes = db.relationship("Transaction", backref="user", lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    valor_pontos = db.Column(db.Integer, nullable=False)
    imagem_url = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(60), nullable=False)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    pontos = db.Column(db.Integer, nullable=False)
    data = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    descricao = db.Column(db.String(255), nullable=False)
    # Status: 'aprovado' (créditos), 'pendente' (resgate aguardando), 'concluido' (prêmio entregue), 'reprovado'
    status = db.Column(db.String(20), nullable=False, default='aprovado')
