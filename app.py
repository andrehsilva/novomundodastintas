import csv
import os
from datetime import datetime
from io import StringIO

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import Product, Transaction, User, db

from supabase import create_client

# Inicializa o cliente Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)
bucket_name = "premios_tintas"



app = Flask(__name__)
#app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
# app.py
# Altere a linha da URI para:
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
db.init_app(app)

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Rotas de Autenticação ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        user = User.query.filter_by(email=email).first()
        
        if user and user.senha_hash == senha:
            if not user.ativo and user.role != 'admin':
                flash("Sua conta aguarda ativação pelo administrador.", "warning")
                return redirect(url_for("login"))
                
            login_user(user)
            return redirect(url_for("index"))
        
        flash("E-mail ou senha inválidos.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if User.query.filter_by(email=request.form.get("email")).first():
            flash("Este e-mail já está cadastrado.", "error")
            return redirect(url_for("register"))

        novo_usuario = User(
            nome=request.form.get("nome"),
            email=request.form.get("email"),
            cpf_cnpj=request.form.get("cpf_cnpj"),
            senha_hash=request.form.get("senha"), 
            role='pintor',
            ativo=False 
        )
        db.session.add(novo_usuario)
        db.session.commit()
        flash("Cadastro realizado com sucesso! Aguarde a ativação pela loja.", "info")
        return redirect(url_for("login"))
    
    return render_template("register.html")

# --- Funções Auxiliares ---

def registrar_transacao(user: User, pontos: int, descricao: str) -> None:
    transacao = Transaction(
        user_id=user.id,
        pontos=pontos,
        descricao=descricao,
        data=datetime.utcnow(),
    )
    user.saldo_total += pontos
    db.session.add(transacao)

def parse_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# --- Rotas Principais ---

@app.route("/")
def index():
    if current_user.is_authenticated:
        # Se for admin, redireciona para a gestão de usuários (trava a dashboard)
        if current_user.role == 'admin':
            return redirect(url_for("admin_usuarios"))
            
        # Se for pintor, mostra a dashboard normal
        transacoes = (
            Transaction.query.filter_by(user_id=current_user.id)
            .order_by(Transaction.data.desc())
            .limit(10)
            .all()
        )
        return render_template("index.html", user=current_user, transacoes=transacoes)
    
    # Se não estiver logado, mostra o catálogo para visitantes
    return redirect(url_for("catalogo"))

@app.route("/catalogo")
def catalogo():
    categoria_slug = request.args.get('categoria')
    ordem = request.args.get('ordem')

    query = Product.query
    if categoria_slug:
        query = query.filter_by(categoria=categoria_slug)

    if ordem == 'asc':
        query = query.order_by(Product.valor_pontos.asc())
    elif ordem == 'desc':
        query = query.order_by(Product.valor_pontos.desc())
    else:
        query = query.order_by(Product.valor_pontos.asc())

    produtos = query.all()
    categorias = [c[0] for c in db.session.query(Product.categoria).distinct().all()]

    return render_template("catalogo.html", 
                           produtos=produtos, 
                           categorias=categorias, 
                           categoria_atual=categoria_slug, 
                           ordem_atual=ordem)

@app.route("/extrato")
@login_required
def extrato():
    transacoes = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.data.desc())
        .all()
    )
    return render_template("extrato.html", user=current_user, transacoes=transacoes)

# --- Painel Administrativo ---

@app.route("/admin/usuarios", methods=["GET", "POST"])
@login_required
def admin_usuarios():
    if current_user.role != 'admin':
        return redirect(url_for("index"))

    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "credito_manual":
            user_id = request.form.get("user_id")
            pontos = parse_int(request.form.get("pontos"), 0)
            alvo = User.query.get(user_id)
            if alvo and pontos != 0:
                registrar_transacao(alvo, pontos, request.form.get("descricao", "Crédito manual"))
                db.session.commit()
                flash(f"Pontos creditados para {alvo.nome}!", "success")
        return redirect(url_for("admin_usuarios"))

    pintores = User.query.filter_by(role='pintor', ativo=True).all()
    pendentes = User.query.filter_by(role='pintor', ativo=False).all()
    transacoes = Transaction.query.order_by(Transaction.data.desc()).all()
    return render_template("admin_usuarios.html", pintores=pintores, pintores_pendentes=pendentes, transacoes_todas=transacoes)

@app.route("/admin/usuarios/novo", methods=["POST"])
@login_required
def admin_novo_usuario():
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    email = request.form.get("email")
    if User.query.filter_by(email=email).first():
        flash("E-mail já cadastrado.", "error")
    else:
        novo = User(
            nome=request.form.get("nome"),
            email=email,
            cpf_cnpj=request.form.get("cpf_cnpj"),
            senha_hash=request.form.get("senha"),
            role='pintor',
            ativo=True # Admin criando já nasce ativo
        )
        db.session.add(novo)
        db.session.commit()
        flash(f"Usuário {novo.nome} criado com sucesso!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/editar/<int:id>", methods=["POST"])
@login_required
def admin_editar_usuario(id):
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    u = User.query.get_or_404(id)
    u.nome = request.form.get("nome")
    u.email = request.form.get("email")
    u.cpf_cnpj = request.form.get("cpf_cnpj")
    if request.form.get("senha"): # Só altera senha se preenchido
        u.senha_hash = request.form.get("senha")
    
    db.session.commit()
    flash("Dados atualizados!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/deletar/<int:id>", methods=["POST"])
@login_required
def admin_deletar_usuario(id):
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    u = User.query.get_or_404(id)
    if u.id == current_user.id:
        flash("Você não pode deletar sua própria conta.", "error")
    else:
        db.session.delete(u)
        db.session.commit()
        flash("Usuário removido.", "warning")
    return redirect(url_for("admin_usuarios"))




@app.route("/admin/premios", methods=["GET", "POST"])
@login_required
def admin_premios():
    if current_user.role != 'admin':
        return redirect(url_for("index"))

    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "cadastrar_produto":
            file = request.files.get("imagem_file")
            if file and allowed_file(file.filename):
                filename = f"{datetime.now().timestamp()}_{file.filename}"
                filepath = f"public/{filename}"
                
                # Upload para o Supabase Storage
                content = file.read()
                supabase.storage.from_(bucket_name).upload(filepath, content)
                
                # Gera a URL pública do arquivo
                imagem_url = supabase.storage.from_(bucket_name).get_public_url(filepath)

                novo = Product(
                    nome=request.form.get("nome"),
                    descricao=request.form.get("descricao"),
                    valor_pontos=parse_int(request.form.get("valor_pontos"), 0),
                    categoria=request.form.get("categoria"),
                    imagem_url=imagem_url # Agora salva a URL completa da nuvem
                )
                db.session.add(novo)
                db.session.commit()
                flash("Prêmio cadastrado no Supabase!", "success")
            else:
                flash("Arquivo inválido.", "error")
        return redirect(url_for("admin_premios"))

@app.route("/admin/confirmar_entrega/<int:id>", methods=["POST"])
@login_required
def admin_confirmar_entrega(id):
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    t = Transaction.query.get_or_404(id)
    t.status = 'entregue'  # Atualiza para o status final de entrega física
    db.session.commit()
    
    flash(f"Entrega do prêmio '{t.descricao}' registrada com sucesso!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/excluir_produto/<int:id>", methods=["POST"])
@login_required
def excluir_produto(id):
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    produto = Product.query.get_or_404(id)
    nome_prod = produto.nome
    db.session.delete(produto)
    db.session.commit()
    flash(f"Produto '{nome_prod}' removido do catálogo.", "warning")
    return redirect(url_for("admin_premios")) # CORRIGIDO: Redireciona para premios

@app.route("/ativar_usuario/<int:id>", methods=["POST"])
@login_required
def ativar_usuario(id):
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    u = User.query.get_or_404(id)
    u.ativo = True
    db.session.commit()
    flash(f"Pintor {u.nome} ativado!", "success")
    return redirect(url_for("admin_usuarios")) # CORRIGIDO: Redireciona para usuarios

# --- Inicialização ---

def seed_data() -> None:
    admin = User.query.filter_by(email="admin@admin.com").first()
    if not admin:
        admin_user = User(
            nome="Administrador", email="admin@admin.com", cpf_cnpj="00000000000",
            senha_hash="admin", role="admin", ativo=True, saldo_total=0
        )
        db.session.add(admin_user)
        db.session.commit()

    if Product.query.count() == 0:
        produtos_iniciais = [
            Product(nome="Vale Compras R$ 50", descricao="Use no próximo pedido.", valor_pontos=2000, 
                    imagem_url="https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?w=400", categoria="Vale"),
            Product(nome="Kit Pintura Premium", descricao="Profissional completo.", valor_pontos=3500, 
                    imagem_url="https://images.unsplash.com/photo-1631209121750-a9f656d8f7e6?w=400", categoria="Ferramenta"),
        ]
        db.session.add_all(produtos_iniciais)
        db.session.commit()


@app.route("/resgatar/<int:produto_id>", methods=["POST"])
@login_required
def resgatar_produto(produto_id):
    if current_user.role != 'pintor':
        return redirect(url_for("index"))
    
    produto = Product.query.get_or_404(produto_id)
    
    if current_user.saldo_total < produto.valor_pontos:
        flash("Saldo insuficiente para este resgate.", "error")
        return redirect(url_for("catalogo"))

    # Criar transação pendente (negativa)
    transacao = Transaction(
        user_id=current_user.id,
        pontos=-produto.valor_pontos,
        descricao=f"Resgate: {produto.nome}",
        status='pendente'
    )
    # Deduzir do saldo imediatamente para "reservar" os pontos
    current_user.saldo_total -= produto.valor_pontos
    
    db.session.add(transacao)
    db.session.commit()
    
    flash("Solicitação de resgate enviada! Aguarde a aprovação da loja.", "success")
    return redirect(url_for("extrato"))

@app.route("/admin/aprovar_resgate/<int:id>/<string:acao>", methods=["POST"])
@login_required
def admin_aprovar_resgate(id, acao):
    if current_user.role != 'admin':
        return redirect(url_for("index"))
    
    t = Transaction.query.get_or_404(id)
    user = User.query.get(t.user_id)

    if acao == "confirmar":
        t.status = 'concluido'
        flash(f"Resgate de {user.nome} confirmado!", "success")
    elif acao == "reprovar":
        # Devolve os pontos ao usuário
        user.saldo_total += abs(t.pontos)
        t.status = 'reprovado'
        flash(f"Resgate de {user.nome} reprovado. Pontos devolvidos.", "warning")
    
    db.session.commit()
    return redirect(url_for("admin_usuarios"))


with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(debug=True)