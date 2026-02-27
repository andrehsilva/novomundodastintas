from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'user_tintas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    # Telefone agora é o identificador único para login
    telefone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True) # E-mail torna-se opcional
    cpf_cnpj = db.Column(db.String(20), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    saldo_total = db.Column(db.Integer, nullable=False, default=0)
    role = db.Column(db.String(20), nullable=False, default='pintor') 
    ativo = db.Column(db.Boolean, default=False) 

    transacoes = db.relationship("Transaction", backref="user_obj", lazy=True)

    
class Product(db.Model):
    __tablename__ = 'product_tintas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    valor_pontos = db.Column(db.Integer, nullable=False)
    imagem_url = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(60), nullable=False)

class Transaction(db.Model):
    __tablename__ = 'transaction_tintas'
    id = db.Column(db.Integer, primary_key=True)
    
    # Referência correta para a tabela user_tintas
    user_id = db.Column(db.Integer, db.ForeignKey("user_tintas.id"), nullable=False)
    
    pontos = db.Column(db.Integer, nullable=False)
    data = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    descricao = db.Column(db.String(255), nullable=False)
    
    # Status: 'aprovado', 'pendente', 'concluido', 'entregue', 'reprovado'
    status = db.Column(db.String(20), nullable=False, default='aprovado')

    # REMOVIDO: user = db.relationship(...) 
    # A relação já é criada pelo backref="user_obj" na classe User acima para evitar conflitos.