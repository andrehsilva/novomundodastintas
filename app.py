import csv
import os
import re
from datetime import datetime
from io import StringIO

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models import Product, Transaction, User, db
from supabase import create_client

# --- Inicialização do Cliente Supabase ---
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)
bucket_name = "premios_tintas"

app = Flask(__name__)
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
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def only_digits(s: str | None) -> str:
    """Remove qualquer caractere não numérico do telefone para busca no banco."""
    if not s:
        return ""
    return re.sub(r"\D+", "", s)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Rotas de Autenticação ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        identificador = (request.form.get("telefone") or "").strip()
        senha = request.form.get("senha") or ""
        
        # Limpa o telefone para bater com o padrão salvo (apenas dígitos)
        telefone_limpo = only_digits(identificador)

        # Busca por telefone normalizado ou por email
        user = None
        if telefone_limpo:
            user = User.query.filter_by(telefone=telefone_limpo).first()
        if not user:
            user = User.query.filter_by(email=identificador.lower()).first()

        # Validação simples (comparação direta para senhas legíveis ou hash se preferir)
        if user and user.senha_hash == senha:
            if not user.ativo and user.role != 'admin':
                flash("Aguarde a ativação da sua conta.", "warning")
                return redirect(url_for("login"))
            
            login_user(user)
            return redirect(url_for("index"))
        
        flash("Credenciais inválidas.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        # Normaliza telefone antes de salvar
        telefone = only_digits(request.form.get("telefone"))
        email_raw = request.form.get("email")
        email = email_raw if email_raw and email_raw.strip() != "" else None
        
        if User.query.filter_by(telefone=telefone).first():
            flash("Este telefone já está cadastrado.", "error")
            return redirect(url_for("register"))

        novo_usuario = User(
            nome=request.form.get("nome"),
            telefone=telefone,
            email=email,
            cpf_cnpj=request.form.get("cpf_cnpj"),
            senha_hash=request.form.get("senha"), 
            role='pintor',
            ativo=False # Requer aprovação do admin
        )
        
        db.session.add(novo_usuario)
        db.session.commit()
        flash("Cadastro solicitado! Aguarde a ativação pela loja.", "info")
        return redirect(url_for("login"))
    
    return render_template("register.html")

@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        telefone = only_digits(request.form.get("telefone"))
        user = User.query.filter_by(telefone=telefone).first()
        if user:
            flash("Solicitação enviada! Entre em contato com a loja para sua nova senha.", "info")
        else:
            flash("Telefone não encontrado.", "error")
    return render_template("esqueci_senha.html")

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
    if current_user.role != 'admin': return redirect(url_for("index"))
    
    telefone = only_digits(request.form.get("telefone"))
    email_raw = request.form.get("email")
    email = email_raw if email_raw and email_raw.strip() != "" else None
    
    if User.query.filter_by(telefone=telefone).first():
        flash("Este telefone já está cadastrado.", "error")
    else:
        novo = User(
            nome=request.form.get("nome"),
            telefone=telefone,
            email=email,
            cpf_cnpj=request.form.get("cpf_cnpj") or None,
            senha_hash=request.form.get("senha") or None,
            role='pintor',
            ativo=True # Admin criando já nasce ativo
        )
        db.session.add(novo)
        db.session.commit()
        flash(f"Profissional {novo.nome} cadastrado com sucesso!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/editar/<int:id>", methods=["POST"])
@login_required
def admin_editar_usuario(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    u = User.query.get_or_404(id)
    u.nome = request.form.get("nome")
    u.email = request.form.get("email") if request.form.get("email") else None
    u.cpf_cnpj = request.form.get("cpf_cnpj")
    u.telefone = only_digits(request.form.get("telefone"))
    if request.form.get("senha"):
        u.senha_hash = request.form.get("senha")
    db.session.commit()
    flash("Dados atualizados!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/deletar/<int:id>", methods=["POST"])
@login_required
def admin_deletar_usuario(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    u = User.query.get_or_404(id)
    if u.id == current_user.id:
        flash("Você não pode deletar sua própria conta.", "error")
    else:
        db.session.delete(u)
        db.session.commit()
        flash("Usuário removido.", "warning")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/resetar-senha/<int:id>", methods=["POST"])
@login_required
def admin_resetar_senha(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    user = User.query.get_or_404(id)
    nova_senha = request.form.get("nova_senha")
    if nova_senha:
        user.senha_hash = nova_senha
        db.session.commit()
        flash(f"Senha de {user.nome} alterada com sucesso!", "success")
    return redirect(url_for("admin_usuarios"))

# --- Gestão de Prêmios ---

@app.route("/admin/premios", methods=["GET", "POST"])
@login_required
def admin_premios():
    if current_user.role != 'admin': return redirect(url_for("index"))
    if request.method == "POST":
        file = request.files.get("imagem_file")
        if file and allowed_file(file.filename):
            filename = f"{datetime.now().timestamp()}_{file.filename}"
            filepath = f"public/{filename}"
            supabase.storage.from_(bucket_name).upload(filepath, file.read())
            imagem_url = supabase.storage.from_(bucket_name).get_public_url(filepath)
            novo = Product(
                nome=request.form.get("nome"),
                descricao=request.form.get("descricao"),
                valor_pontos=parse_int(request.form.get("valor_pontos"), 0),
                categoria=request.form.get("categoria"),
                imagem_url=imagem_url
            )
            db.session.add(novo)
            db.session.commit()
            flash("Prêmio cadastrado!", "success")
        return redirect(url_for("admin_premios"))
    produtos = Product.query.order_by(Product.nome).all()
    return render_template("admin_premios.html", produtos=produtos)

@app.route("/admin/excluir_produto/<int:id>", methods=["POST"])
@login_required
def excluir_produto(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    produto = Product.query.get_or_404(id)
    db.session.delete(produto)
    db.session.commit()
    flash("Produto removido!", "warning")
    return redirect(url_for("admin_premios"))

# --- Fluxo de Resgates e Ativação ---

@app.route("/ativar_usuario/<int:id>", methods=["POST"])
@login_required
def ativar_usuario(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    u = User.query.get_or_404(id)
    u.ativo = True
    db.session.commit()
    flash(f"Pintor {u.nome} ativado!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/resgatar/<int:produto_id>", methods=["POST"])
@login_required
def resgatar_produto(produto_id):
    if current_user.role != 'pintor': return redirect(url_for("index"))
    produto = Product.query.get_or_404(produto_id)
    if current_user.saldo_total < produto.valor_pontos:
        flash("Saldo insuficiente.", "error")
        return redirect(url_for("catalogo"))
    transacao = Transaction(
        user_id=current_user.id, pontos=-produto.valor_pontos,
        descricao=f"Resgate: {produto.nome}", status='pendente'
    )
    current_user.saldo_total -= produto.valor_pontos
    db.session.add(transacao)
    db.session.commit()
    flash("Solicitação de resgate enviada!", "success")
    return redirect(url_for("extrato"))

@app.route("/admin/aprovar_resgate/<int:id>/<string:acao>", methods=["POST"])
@login_required
def admin_aprovar_resgate(id, acao):
    if current_user.role != 'admin': return redirect(url_for("index"))
    t = Transaction.query.get_or_404(id)
    user = User.query.get(t.user_id)
    if acao == "confirmar":
        t.status = 'concluido'
    elif acao == "reprovar":
        user.saldo_total += abs(t.pontos)
        t.status = 'reprovado'
    db.session.commit()
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/confirmar_entrega/<int:id>", methods=["POST"])
@login_required
def admin_confirmar_entrega(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    t = Transaction.query.get_or_404(id)
    t.status = 'entregue'
    db.session.commit()
    flash("Entrega confirmada!", "success")
    return redirect(url_for("admin_usuarios"))

# --- Rotas Principais ---

@app.route("/")
@login_required
def index():
    if current_user.role == 'admin':
        return redirect(url_for("admin_usuarios"))
    
    posicao_superior = User.query.filter(
        User.role == 'pintor',
        User.ativo == True,
        User.saldo_total > current_user.saldo_total
    ).count()

    # Removido o .limit(10) para mostrar o histórico completo
    transacoes = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.data.desc()).all()
    
    return render_template("index.html", 
                           user=current_user, 
                           transacoes=transacoes, 
                           competidores_acima=posicao_superior)

@app.route("/catalogo")
def catalogo():
    # Captura os parâmetros da URL
    categoria_selecionada = request.args.get('categoria')
    ordem_selecionada = request.args.get('ordem', 'asc') # 'asc' é o padrão se não houver clique
    
    query = Product.query
    
    # Aplica o filtro de categoria se existir
    if categoria_selecionada:
        query = query.filter_by(categoria=categoria_selecionada)
    
    # Aplica a ordenação correta baseada no clique do usuário
    if ordem_selecionada == 'desc':
        query = query.order_by(Product.valor_pontos.desc())
    else:
        query = query.order_by(Product.valor_pontos.asc())
    
    produtos = query.all()
    
    # Busca categorias únicas para preencher o seletor
    categorias = [c[0] for c in db.session.query(Product.categoria).distinct().all() if c[0]]
    
    return render_template("catalogo.html", 
                           produtos=produtos, 
                           categorias=categorias, 
                           categoria_ativa=categoria_selecionada,
                           ordem_atual=ordem_selecionada) # Passa a ordem atual para manter o seletor marcado

@app.route("/extrato")
@login_required
def extrato():
    transacoes = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.data.desc()).all()
    return render_template("extrato.html", user=current_user, transacoes=transacoes)


@app.route("/regulamento")
def regulamento():
    return render_template("regulamento.html")

# --- Funções Internas e Inicialização ---

def registrar_transacao(user: User, pontos: int, descricao: str) -> None:
    transacao = Transaction(user_id=user.id, pontos=pontos, descricao=descricao)
    user.saldo_total += pontos
    db.session.add(transacao)

def parse_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def seed_data() -> None:
    if not User.query.filter_by(role="admin").first():
        admin = User(
            nome="Administrador", email="admin@admin.com", telefone="9999999999",
            senha_hash="admin", role="admin", ativo=True
        )
        db.session.add(admin)
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(debug=True)