import os
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import Product, Transaction, User, db
from supabase import create_client

app = Flask(__name__)

# --- Configurações de Banco e Segurança ---
# Lembre-se de configurar estas variáveis no EasyPanel
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
db.init_app(app)

# --- Inicialização do Supabase Storage ---
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
bucket_name = "premios_tintas"

# Inicializa o cliente apenas se as chaves existirem para evitar erro no boot
if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
else:
    supabase = None

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Funções Auxiliares de Lógica ---

def registrar_transacao(user: User, pontos: int, descricao: str) -> None:
    """Registra movimentação de pontos e atualiza o saldo do usuário."""
    transacao = Transaction(
        user_id=user.id,
        pontos=pontos,
        descricao=descricao,
        data=datetime.utcnow(),
        status='aprovado' if pontos > 0 else 'pendente'
    )
    user.saldo_total += pontos
    db.session.add(transacao)

def parse_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

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

# --- Rotas do Usuário (Pintor) ---

@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for("admin_usuarios"))
            
        transacoes = (
            Transaction.query.filter_by(user_id=current_user.id)
            .order_by(Transaction.data.desc())
            .limit(10)
            .all()
        )
        return render_template("index.html", user=current_user, transacoes=transacoes)
    return redirect(url_for("catalogo"))

@app.route("/catalogo")
def catalogo():
    categoria_slug = request.args.get('categoria')
    ordem = request.args.get('ordem')
    query = Product.query

    if categoria_slug:
        query = query.filter_by(categoria=categoria_slug)

    if ordem == 'desc':
        query = query.order_by(Product.valor_pontos.desc())
    else:
        query = query.order_by(Product.valor_pontos.asc())

    produtos = query.all()
    categorias = [c[0] for c in db.session.query(Product.categoria).distinct().all()]

    return render_template("catalogo.html", produtos=produtos, categorias=categorias, 
                           categoria_atual=categoria_slug, ordem_atual=ordem)

@app.route("/resgatar/<int:produto_id>", methods=["POST"])
@login_required
def resgatar_produto(produto_id):
    if current_user.role != 'pintor':
        return redirect(url_for("index"))
    
    produto = Product.query.get_or_404(produto_id)
    if current_user.saldo_total < produto.valor_pontos:
        flash("Saldo insuficiente para este resgate.", "error")
        return redirect(url_for("catalogo"))

    transacao = Transaction(
        user_id=current_user.id,
        pontos=-produto.valor_pontos,
        descricao=f"Resgate: {produto.nome}",
        status='pendente'
    )
    current_user.saldo_total -= produto.valor_pontos
    db.session.add(transacao)
    db.session.commit()
    flash("Solicitação de resgate enviada!", "success")
    return redirect(url_for("extrato"))

@app.route("/extrato")
@login_required
def extrato():
    transacoes = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.data.desc()).all()
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

@app.route("/admin/premios", methods=["GET", "POST"])
@login_required
def admin_premios():
    if current_user.role != 'admin':
        return redirect(url_for("index"))

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
            flash("Prêmio cadastrado com sucesso!", "success")
        else:
            flash("Erro no arquivo de imagem.", "error")
        return redirect(url_for("admin_premios"))

    produtos = Product.query.order_by(Product.nome).all()
    return render_template("admin_premios.html", produtos=produtos)

@app.route("/admin/aprovar_resgate/<int:id>/<string:acao>", methods=["POST"])
@login_required
def admin_aprovar_resgate(id, acao):
    if current_user.role != 'admin': return redirect(url_for("index"))
    t = Transaction.query.get_or_404(id)
    u = User.query.get(t.user_id)

    if acao == "confirmar":
        t.status = 'concluido'
        flash(f"Resgate de {u.nome} aprovado!", "success")
    elif acao == "reprovar":
        u.saldo_total += abs(t.pontos)
        t.status = 'reprovado'
        flash(f"Resgate reprovado. Pontos devolvidos.", "warning")
    db.session.commit()
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/confirmar_entrega/<int:id>", methods=["POST"])
@login_required
def admin_confirmar_entrega(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    t = Transaction.query.get_or_404(id)
    t.status = 'entregue'
    db.session.commit()
    flash("Entrega registrada!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/ativar_usuario/<int:id>", methods=["POST"])
@login_required
def ativar_usuario(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    u = User.query.get_or_404(id)
    u.ativo = True
    db.session.commit()
    flash(f"Pintor {u.nome} ativado!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/excluir_produto/<int:id>", methods=["POST"])
@login_required
def excluir_produto(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    p = Product.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    flash("Produto removido.", "warning")
    return redirect(url_for("admin_premios"))

# --- Inicialização e Seed de Dados ---

def seed_data():
    """Cria o admin inicial e produtos básicos se o banco estiver vazio."""
    if not User.query.filter_by(role='admin').first():
        admin = User(
            nome="Administrador", email="admin@admin.com", cpf_cnpj="00000000000",
            senha_hash="admin", role="admin", ativo=True
        )
        db.session.add(admin)
    
    if Product.query.count() == 0:
        p1 = Product(nome="Vale Compras R$ 50", descricao="Vale uso imediato", valor_pontos=2000, 
                     imagem_url="https://via.placeholder.com/400", categoria="Vale")
        db.session.add(p1)
    db.session.commit()

with app.app_context():
    db.create_all() # Cria as tabelas _tintas no Supabase
    seed_data()

if __name__ == "__main__":
    app.run(debug=True)