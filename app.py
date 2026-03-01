import csv
import os
from datetime import datetime
from io import StringIO

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import Product, Transaction, User, db
from supabase import create_client

# --- Inicialização ---
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)
bucket_name = "premios_tintas"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

def seed_data() -> None:
    admin = User.query.filter_by(role="admin").first()
    if not admin:
        admin_user = User(
            nome="Administrador", email="admin@admin.com", cpf_cnpj="00000000000",
            telefone="00000000000", senha_hash="admin", role="admin", ativo=True
        )
        db.session.add(admin_user)
        db.session.commit()

# --- Rotas de Autenticação ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        identificador = request.form.get("telefone")
        senha = request.form.get("senha")
        user = User.query.filter_by(telefone=identificador).first() or \
               User.query.filter_by(email=identificador).first()
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

@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        telefone = request.form.get("telefone")
        user = User.query.filter_by(telefone=telefone).first()
        if user:
            flash("Solicitação enviada! Entre em contato com a loja.", "info")
        else:
            flash("Telefone não encontrado.", "error")
    return render_template("esqueci_senha.html")

# --- Rotas Administrativas ---

@app.route("/admin/usuarios", methods=["GET", "POST"])
@login_required
def admin_usuarios():
    if current_user.role != 'admin': return redirect(url_for("index"))
    if request.method == "POST" and request.form.get("acao") == "credito_manual":
        alvo = User.query.get(request.form.get("user_id"))
        pts = parse_int(request.form.get("pontos"))
        if alvo and pts != 0:
            registrar_transacao(alvo, pts, request.form.get("descricao", "Crédito manual"))
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
    tel = request.form.get("telefone")
    email_raw = request.form.get("email")
    email = email_raw if email_raw and email_raw.strip() != "" else None
    if User.query.filter_by(telefone=tel).first():
        flash("Este telefone já está cadastrado.", "error")
    else:
        novo = User(
            nome=request.form.get("nome"), telefone=tel, email=email,
            cpf_cnpj=request.form.get("cpf_cnpj") or None,
            senha_hash=request.form.get("senha") or None,
            role='pintor', ativo=True
        )
        db.session.add(novo)
        db.session.commit()
        flash(f"Profissional {novo.nome} cadastrado com sucesso!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/resetar-senha/<int:id>", methods=["POST"])
@login_required
def admin_resetar_senha(id):
    if current_user.role != 'admin': return redirect(url_for("index"))
    user = User.query.get_or_404(id)
    nova = request.form.get("nova_senha")
    if nova:
        user.senha_hash = nova
        db.session.commit()
        flash(f"Senha de {user.nome} alterada!", "success")
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/premios", methods=["GET", "POST"])
@login_required
def admin_premios():
    if current_user.role != 'admin': return redirect(url_for("index"))
    if request.method == "POST" and request.form.get("acao") == "cadastrar_produto":
        file = request.files.get("imagem_file")
        if file and allowed_file(file.filename):
            filename = f"{datetime.now().timestamp()}_{file.filename}"
            filepath = f"public/{filename}"
            supabase.storage.from_(bucket_name).upload(filepath, file.read())
            imagem_url = supabase.storage.from_(bucket_name).get_public_url(filepath)
            novo = Product(
                nome=request.form.get("nome"), descricao=request.form.get("descricao"),
                valor_pontos=parse_int(request.form.get("valor_pontos")),
                categoria=request.form.get("categoria"), imagem_url=imagem_url
            )
            db.session.add(novo)
            db.session.commit()
            flash("Prêmio cadastrado!", "success")
        return redirect(url_for("admin_premios"))
    produtos = Product.query.order_by(Product.nome).all()
    return render_template("admin_premios.html", produtos=produtos)

# --- Rotas de Fluxo de Prêmios ---

@app.route("/resgatar/<int:produto_id>", methods=["POST"])
@login_required
def resgatar_produto(produto_id):
    prod = Product.query.get_or_404(produto_id)
    if current_user.saldo_total < prod.valor_pontos:
        flash("Saldo insuficiente.", "error")
        return redirect(url_for("catalogo"))
    transacao = Transaction(user_id=current_user.id, pontos=-prod.valor_pontos, descricao=f"Resgate: {prod.nome}", status='pendente')
    current_user.saldo_total -= prod.valor_pontos
    db.session.add(transacao)
    db.session.commit()
    flash("Solicitação enviada!", "success")
    return redirect(url_for("extrato"))

@app.route("/admin/aprovar_resgate/<int:id>/<string:acao>", methods=["POST"])
@login_required
def admin_aprovar_resgate(id, acao):
    t = Transaction.query.get_or_404(id)
    u = User.query.get(t.user_id)
    if acao == "confirmar":
        t.status = 'concluido'
        flash("Resgate confirmado!", "success")
    elif acao == "reprovar":
        u.saldo_total += abs(t.pontos)
        t.status = 'reprovado'
        flash("Resgate reprovado e pontos devolvidos.", "warning")
    db.session.commit()
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/confirmar_entrega/<int:id>", methods=["POST"])
@login_required
def admin_confirmar_entrega(id):
    t = Transaction.query.get_or_404(id)
    t.status = 'entregue'
    db.session.commit()
    flash("Entrega registrada!", "success")
    return redirect(url_for("admin_usuarios"))

# --- Rotas Gerais ---

@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin': return redirect(url_for("admin_usuarios"))
        transacoes = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.data.desc()).limit(10).all()
        return render_template("index.html", user=current_user, transacoes=transacoes)
    return redirect(url_for("catalogo"))

@app.route("/catalogo")
def catalogo():
    produtos = Product.query.order_by(Product.valor_pontos.asc()).all()
    categorias = [c[0] for c in db.session.query(Product.categoria).distinct().all()]
    return render_template("catalogo.html", produtos=produtos, categorias=categorias)

@app.route("/extrato")
@login_required
def extrato():
    transacoes = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.data.desc()).all()
    return render_template("extrato.html", user=current_user, transacoes=transacoes)

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(debug=True)