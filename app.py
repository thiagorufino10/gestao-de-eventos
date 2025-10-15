import os
import re
import json
import io
from uuid import uuid4
from datetime import datetime, timedelta
from urllib.parse import urlencode
from decimal import Decimal
import bcrypt
import mysql.connector
import pandas as pd
import requests
from flask import (Flask, abort, flash, jsonify, make_response, redirect,
                   render_template, request, session, url_for)
from flask_cors import CORS
from flask_mail import Mail, Message
from mysql.connector import errors as mysql_errors
from werkzeug.utils import secure_filename
import collections
from db import close_connection, create_initial_admin_user, get_db
from dotenv import load_dotenv








load_dotenv()  # Carrega variáveis de ambiente do arquivo .env

# Recupera a senha de admin de forma segura
admin_password = os.getenv('ADMIN_PASSWORD')

hashed_password = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt())
# ===================================
# INICIALIZAÇÃO E CONFIGURAÇÃO DO APP
# ===================================
app = Flask(__name__)
CORS(app)
app.secret_key = os.urandom(24)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

# ==============================================================================
# CARREGAR CONFIGURAÇÕES DE E-MAIL DO BANCO DE DADOS
# ==============================================================================
def carregar_configuracoes_email():
    with app.app_context():  # Garantir que estamos dentro do contexto da aplicação Flask
        db = get_db()  # Conectar ao banco de dados
        cursor = db.cursor(dictionary=True)
        try:
            # Tenta buscar a última configuração de e-mail salva no banco
            cursor.execute("SELECT email, codigo_app FROM configuracoes_email ORDER BY id DESC LIMIT 1")
            configuracao_email = cursor.fetchone()

            if configuracao_email:
                # Aqui, pegamos o e-mail e a senha de app cadastrados no banco e aplicamos no Flask-Mail
                app.config['MAIL_USERNAME'] = configuracao_email['email']
                app.config['MAIL_PASSWORD'] = configuracao_email['codigo_app']
            else:
                # Caso não haja configuração no banco, defina um valor padrão (para testes)
                app.config['MAIL_USERNAME'] = 'seu_email@gmail.com'
                app.config['MAIL_PASSWORD'] = 'senha_de_app_padrao'

        except Exception as e:
            flash(f"Erro ao carregar as configurações de e-mail: {e}", "error")
            # Caso ocorra erro, configura valores padrão
            app.config['MAIL_USERNAME'] = 'seu_email@gmail.com'
            app.config['MAIL_PASSWORD'] = 'senha_de_app_padrao'
        finally:
            cursor.close()


# ==============================================================================
# CONFIGURAÇÃO DO E-MAIL - USANDO AS CONFIGURAÇÕES CARREGADAS DO BANCO
# ==============================================================================
# Carregar as configurações de e-mail ao iniciar
carregar_configuracoes_email()

# Configuração do Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465  # Usando 465 para SSL
app.config['MAIL_USE_SSL'] = True  # Usar SSL para segurança

mail = Mail(app)  # Inicializa o Flask-Mail com as configurações carregadas

# ==============================================================================
# FINALIZANDO - ASSOCIAÇÃO DA FUNÇÃO DE FECHAMENTO DE CONEXÃO COM O CONTEXTO DA APLICAÇÃO
# ==============================================================================
app.teardown_appcontext(close_connection)  # Fechar a conexão com o banco de dados quando a aplicação terminar



# ========================
# Configurações de Upload
# ========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
PRODUTOS_DIR = os.path.join(UPLOADS_DIR, "produtos")
KITS_DIR = os.path.join(UPLOADS_DIR, "kits")

os.makedirs(PRODUTOS_DIR, exist_ok=True)
os.makedirs(KITS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# ========================
# Funções Utilitárias
# ========================
def only_digits(s):
    return re.sub(r'\D', '', s or '')

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file_storage, subdir: str) -> str | None:
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        return None
    
    fname = secure_filename(file_storage.filename)
    ext = fname.rsplit(".", 1)[1].lower()
    unique = f"{uuid4().hex}.{ext}"
    
    folder = KITS_DIR if subdir == "kits" else PRODUTOS_DIR
    rel_path = f"uploads/{subdir}/{unique}"
    
    file_path = os.path.join(folder, unique)
    file_storage.save(file_path)
    return rel_path

def remove_file_if_exists(rel_path: str):
    if not rel_path: return
    full_path = os.path.join(STATIC_DIR, rel_path.replace("\\", "/"))
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass

# ========================
# Rotas
# ========================

# No seu arquivo app.py

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return render_template("dashboard.html")

    cursor = db.cursor(dictionary=True)
    stats = {}
    
    cursor.execute("SELECT nome_evento, data_evento FROM eventos WHERE data_evento >= CURDATE() ORDER BY data_evento ASC LIMIT 1")
    proximo_evento = cursor.fetchone()

    cursor.execute("SELECT SUM(valor) as total FROM fluxo_caixa WHERE tipo = 'Receita' AND MONTH(data) = MONTH(CURDATE()) AND YEAR(data) = YEAR(CURDATE())")
    receita_mes_result = cursor.fetchone()
    stats['receita_mes'] = receita_mes_result['total'] if receita_mes_result else 0

    cursor.execute("SELECT COUNT(id) as total FROM clientes")
    stats['total_clientes'] = cursor.fetchone()['total'] or 0

    cursor.execute("SELECT SUM(quantidade_estoque) as total FROM estoque")
    stats['total_itens_estoque'] = cursor.fetchone()['total'] or 0

    cursor.execute("SELECT e.nome_evento, c.nome as cliente_nome FROM eventos e JOIN clientes c ON e.cliente_id = c.id ORDER BY e.id DESC LIMIT 5")
    eventos_recentes = cursor.fetchall()

    cursor.execute("SELECT e.nome_evento, e.data_evento, c.nome as cliente_nome, e.status FROM eventos e JOIN clientes c ON e.cliente_id = c.id ORDER BY e.data_evento")
    todos_eventos = cursor.fetchall()
    
    cursor.close()
    return render_template("dashboard.html", stats=stats, proximo_evento=proximo_evento, eventos_recentes=eventos_recentes, todos_eventos=todos_eventos)



from flask import Flask, render_template, session, redirect, url_for, flash, request
from datetime import datetime 

# ... (Seu código de inicialização do Flask e get_db) ...




def registrar_log_status(db, id_evento, novo_status, nome_evento, nome_cliente):
    """Insere um novo registro de mudança de status na tabela log_atividades."""
    cursor = db.cursor()
    descricao = f"Status alterado para '{novo_status}' no evento '{nome_evento}' do cliente {nome_cliente}."
    
    cursor.execute("""
        INSERT INTO log_atividades (tipo, id_referencia, descricao)
        VALUES (%s, %s, %s)
    """, ('MUDANCA_STATUS_EVENTO', id_evento, descricao))
    db.commit()





@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # 1. BUSCAR LOGS DE MUDANÇA DE STATUS (NOVO)
    cursor.execute("""
        SELECT 
            descricao, 
            'LOG_STATUS' as tipo_atividade,
            data_log as data_criacao -- Usamos data_log para ordenação
        FROM log_atividades
        WHERE tipo = 'MUDANCA_STATUS_EVENTO'
        ORDER BY data_log DESC
        LIMIT 5
    """)
    logs_status = cursor.fetchall()

    # 2. BUSCAR EVENTOS RECENTES (Criados - Status Pendente)
    # Mostra os eventos NOVOS (os logs de status já cobrem os avanços)
    cursor.execute("""
        SELECT 
            id, nome_evento, status, data_evento, 
            (SELECT nome FROM clientes WHERE id = cliente_id) as cliente_nome,
            'Evento' as tipo_atividade,
            data_criacao 
        FROM eventos
        WHERE status = 'Pendente' -- Filtra apenas os orçamentos/eventos novos (Pendente)
        ORDER BY data_criacao DESC
        LIMIT 5
    """)
    eventos_recentes = cursor.fetchall()

    # 3. BUSCAR PRODUTOS RECENTES (Cadastrados)
    cursor.execute("""
        SELECT 
            nome AS nome_produto, 
            quantidade_estoque, 
            'Produto' as tipo_atividade,
            data_cadastro as data_criacao -- Alias para unificar a chave de ordenação
        FROM estoque
        ORDER BY data_cadastro DESC
        LIMIT 5
    """)
    produtos_recentes = cursor.fetchall()
    
    # 4. UNIR E ORDENAR
    # Unimos os 3 tipos de atividades.
    todas_atividades = logs_status + eventos_recentes + produtos_recentes

    # Função de ordenação: Usa 'data_criacao' (que agora é data_log para logs e data_cadastro para produtos)
    def get_sort_key(atividade):
        return atividade.get('data_criacao')
    
    atividades_validas = [a for a in todas_atividades if get_sort_key(a) is not None]
    
    atividades_validas.sort(key=get_sort_key, reverse=True)
    
    ultimas_atividades = atividades_validas[:10]

    # --- CÓDIGO PARA OBTER VARIÁVEIS DO CONTEXTO DO TEMPLATE (Mantido) ---
    cursor.execute("SELECT id, nome_evento, data_evento, cliente_id, status FROM eventos")
    todos_eventos = cursor.fetchall()

    cursor.execute("""
        SELECT nome_evento, data_evento 
        FROM eventos 
        WHERE data_evento >= CURDATE() AND status = 'Confirmado'
        ORDER BY data_evento ASC
        LIMIT 1
    """)
    proximo_evento = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(id) AS total_clientes FROM clientes")
    total_clientes = cursor.fetchone().get('total_clientes', 0)

    cursor.execute("SELECT SUM(quantidade_estoque) AS total_itens_estoque FROM estoque")
    total_itens_estoque = cursor.fetchone().get('total_itens_estoque', 0)
    
    stats = {
        'receita_mes': 0.00, # Adapte com a sua consulta real
        'total_clientes': total_clientes,
        'total_itens_estoque': total_itens_estoque
    }
    # --- FIM do código de contexto ---
    
    return render_template(
        "dashboard.html", 
        ultimas_atividades=ultimas_atividades, 
        todos_eventos=todos_eventos, 
        stats=stats,
        proximo_evento=proximo_evento
    )






@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password").encode('utf-8')
        db = get_db()
        if db is None:
            flash("Erro ao conectar ao banco de dados.", 'error')
            return redirect(url_for("login"))
        
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and bcrypt.checkpw(password, user['password'].encode('utf-8')):
            session["logged_in"] = True
            session["username"] = username
            session["role"] = user['role']
            return redirect(url_for("index"))
        else:
            error = "Nome de usuário ou senha inválidos. Tente novamente."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("username", None)
    session.pop("role", None)
    return redirect(url_for("login"))

@app.route("/cadastro_usuario", methods=["GET", "POST"])
def cadastro_usuario():
    if not session.get("logged_in") or session.get("role") != "admin":
        return redirect(url_for("index"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("cadastro_usuario"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password").encode('utf-8')
        role = request.form.get("role")
        hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                           (username, hashed_password.decode('utf-8'), role))
            db.commit()
            cursor.close()
            flash("Usuário cadastrado com sucesso!", 'success')
        except mysql.connector.IntegrityError:
            flash("Nome de usuário já existe. Por favor, escolha outro.", 'error')
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", 'error')

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    cursor.close()
    return render_template("cadastro_usuario.html", users=users)





@app.route("/configurar_email", methods=["GET", "POST"])
def configurar_email():
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", "error")
        return redirect(url_for('configurar_email'))
    
    if request.method == "POST":
        email = request.form.get("email")
        codigo_app = request.form.get("codigo_app")

        # Salve as configurações no banco de dados
        try:
            cursor = db.cursor()
            # Atualiza ou insere as configurações de e-mail
            cursor.execute("""
                INSERT INTO configuracoes_email (email, codigo_app)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE email = %s, codigo_app = %s
            """, (email, codigo_app, email, codigo_app))
            db.commit()
            flash("Configuração de e-mail salva com sucesso!", "success")
        except Exception as e:
            flash(f"Erro ao salvar as configurações: {e}", "error")
        return redirect(url_for('configurar_email'))  # Redireciona de volta à página de configurações

    # Carregar as configurações de e-mail se já existirem
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT email, codigo_app FROM configuracoes_email ORDER BY id DESC LIMIT 1")
    email_configurado = cursor.fetchone()
    cursor.close()

    return render_template("configurar_email.html", email_configurado=email_configurado)

@app.route("/excluir_email", methods=["POST"])
def excluir_email():
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", "error")
        return redirect(url_for('configurar_email'))
    
    try:
        # Primeiramente, busque o último e-mail configurado
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id FROM configuracoes_email ORDER BY id DESC LIMIT 1")
        email_configurado = cursor.fetchone()

        if email_configurado:
            # Excluir a configuração de e-mail do banco de dados
            cursor.execute("DELETE FROM configuracoes_email WHERE id = %s", (email_configurado['id'],))
            db.commit()
            flash("E-mail excluído com sucesso!", "success")
        else:
            flash("Nenhuma configuração de e-mail encontrada para exclusão.", "error")
    
    except Exception as e:
        db.rollback()
        flash(f"Erro ao excluir o e-mail: {e}", "error")
    finally:
        cursor.close()

    return redirect(url_for('configurar_email'))






# ========================
# ESTOQUE (Produtos)
# ========================
@app.route("/estoque_evento", methods=["GET", "POST"])
def estoque_evento():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("estoque_evento"))

    if request.method == 'POST':
        # Extrai os dados do formulário
        nome = (request.form.get("nome_material") or "").strip().lower()
        tipo_material = request.form.get("tipo_material")
        unidade_medida = request.form.get("unidade_medida") or "unidade"
        quantidade_estoque_str = request.form.get("quantidade_estoque")
        preco_compra_str = request.form.get("preco_compra")
        preco_repasse_str = request.form.get("preco_repasse")
        quantidade_venda_raw = request.form.get("quantidade_venda")
        foto = request.files.get('foto_produto')

        cursor = db.cursor(dictionary=True)
        # Validação de duplicidade de nome
        cursor.execute("SELECT COUNT(*) as count FROM estoque WHERE nome = %s", (nome,))
        if cursor.fetchone()['count'] > 0:
            flash('Material com este nome já existe. Por favor, escolha outro.', 'error')
            cursor.close()
            return redirect(url_for('estoque_evento'))
        
        # Validação e conversão de números
        try:
            quantidade_estoque = float(quantidade_estoque_str) if quantidade_estoque_str else 0.0
            preco_compra = float(preco_compra_str) if preco_compra_str else 0.0
            preco_repasse = float(preco_repasse_str) if preco_repasse_str else 0.0
            
            unidades_com_qtd = {'pacote', 'caixa', 'saco', 'pote'}
            precisa_qtd_por_unidade = unidade_medida in unidades_com_qtd

            if precisa_qtd_por_unidade:
                if not quantidade_venda_raw:
                    raise ValueError("Quantidade por unidade é obrigatória para a combinação selecionada.")
                quantidade_venda = float(quantidade_venda_raw)
                if quantidade_venda <= 0:
                    raise ValueError("Quantidade por unidade deve ser maior que zero.")
            else:
                quantidade_venda = None # Usar NULL no banco para maior clareza
        except (ValueError, TypeError) as e:
            flash(f"Erro nos dados numéricos: {e}", 'error')
            cursor.close()
            return redirect(url_for('estoque_evento'))

        # Salva imagem (se houver)
        foto_path = None
        if foto and foto.filename:
            foto_path = save_image(foto, subdir="produtos")

        try:
            # Inserção do produto
            cursor.execute(
                """
                INSERT INTO estoque 
                    (nome, tipo_material, unidade_medida, quantidade_venda, quantidade_estoque, preco_compra, preco_repasse, foto_path) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (nome, tipo_material, unidade_medida, quantidade_venda, quantidade_estoque, preco_compra, preco_repasse, foto_path)
            )

            # Se o preço de compra for maior que zero, lança como despesa no fluxo de caixa
            if preco_compra > 0 and quantidade_estoque > 0:
                custo_total = preco_compra * quantidade_estoque
                cursor.execute(
                    """
                    INSERT INTO fluxo_caixa (data, descricao, tipo, valor, observacoes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        datetime.now().date(),
                        f"Compra de estoque: {nome.capitalize()}",
                        "Despesa",
                        custo_total,
                        f"Lançamento automático de {quantidade_estoque} unidade(s) a R$ {preco_compra:.2f} cada."
                    )
                )

            db.commit()
            flash("Material cadastrado com sucesso e despesa lançada no fluxo de caixa!", 'success')

        except Exception as e:
            db.rollback()
            if foto_path: remove_file_if_exists(foto_path)
            flash(f"Ocorreu um erro ao salvar o material: {e}", 'error')
        finally:
            cursor.close()
        return redirect(url_for('estoque_evento'))

    # GET - Carrega a página
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM estoque ORDER BY id DESC")
    materiais = cursor.fetchall()
    cursor.close()
    return render_template('estoque_evento.html', materiais=materiais)




# ========================
# ORÇAMENTOS DE EVENTOS
# ========================






# Adicione esta nova rota no seu arquivo app.py, preferencialmente
# perto das rotas de orçamentos (/orcamento_eventos)

@app.route("/reenviar_orcamento/<int:orcamento_id>", methods=["POST"])
def reenviar_orcamento(orcamento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("orcamento_eventos"))

    cursor = db.cursor(dictionary=True)
    try:
        # 1. Buscar detalhes do orçamento e cliente
        cursor.execute("""
            SELECT 
                o.nome_evento, o.data_evento, o.mao_de_obra, o.frete, o.valor_total, o.itens_json, o.token, o.status,
                c.nome AS cliente_nome, c.email AS cliente_email
            FROM orcamentos o
            JOIN clientes c ON o.cliente_id = c.id
            WHERE o.id = %s
        """, (orcamento_id,))
        orcamento = cursor.fetchone()

        if not orcamento:
            flash("Orçamento não encontrado.", "error")
            return redirect(url_for("orcamento_eventos"))

        # ADIÇÃO DA VERIFICAÇÃO DE SEGURANÇA NO BACKEND
        if orcamento['status'] == 'Aprovado':
            flash(f"O orçamento '{orcamento['nome_evento']}' já está APROVADO. O reenvio de e-mail foi bloqueado.", "warning")
            return redirect(url_for("orcamento_eventos"))

        cliente_email = orcamento['cliente_email']
        cliente_nome = orcamento['cliente_nome']
        nome_evento = orcamento['nome_evento']
        data_evento = orcamento['data_evento']
        mao_de_obra = Decimal(orcamento['mao_de_obra'])
        frete = Decimal(orcamento['frete'])
        valor_total = Decimal(orcamento['valor_total'])
        itens_selecionados = json.loads(orcamento['itens_json'])
        token = orcamento['token']

        # 2. Reconstruir detalhes dos itens para o corpo do e-mail
        itens_detalhados_email = ""
        valor_total_itens = Decimal(0)
        
        # ... (O código de reconstrução dos itens e envio de e-mail permanece o mesmo) ...
        
        for item in itens_selecionados:
            # ... (Lógica de busca de itens) ...
            item_id = item['id']
            item_tipo = item['tipo']
            quantidade = item['quantidade']
            
            # ... (Definição de nome e valor_unitario) ...
            nome = ""
            valor_unitario = Decimal(0)

            if item_tipo == 'produto':
                cursor.execute("SELECT nome, preco_repasse FROM estoque WHERE id = %s", (item_id,))
                material_db = cursor.fetchone()
                if material_db:
                    nome = material_db['nome']
                    valor_unitario = Decimal(material_db['preco_repasse'])
            elif item_tipo == 'kit':
                cursor.execute("SELECT nome, valor FROM kits WHERE id = %s", (item_id,))
                material_db = cursor.fetchone()
                if material_db:
                    nome = material_db['nome']
                    valor_unitario = Decimal(material_db['valor'])
            
            if not nome:
                 nome = f"ITEM ID {item_id} ({item_tipo.upper()}) (Removido ou Inválido)"


            valor_total_item = valor_unitario * quantidade
            valor_total_itens += valor_total_item
            
            # Formato HTML do item (reutilizado do envio original)
            itens_detalhados_email += f"""
                <tr>
                    <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">{nome}</td>
                    <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">R$ {valor_unitario:.2f}</td>
                    <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">{quantidade}</td>
                    <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">R$ {valor_total_item:.2f}</td>
                </tr>
            """

        # 3. Gerar Link de Aprovação
        link_aprovacao = url_for('aprovar_orcamento', token=token, _external=True)

        # 4. Formatar data
        data_formatada = ""
        if isinstance(data_evento, datetime):
            data_formatada = data_evento.strftime('%d/%m/%Y às %H:%M')
        else:
             # Tentativa de formatar string se o MySQL não retornar um objeto datetime
             data_formatada = datetime.strptime(str(data_evento).split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y às %H:%M')


        # 5. Re-criar e enviar e-mail
        msg = Message(
            subject=f"[REENVIO] Orçamento para seu evento: {nome_evento}",
            sender="GESTÃO DE EVENTOS <gestao.eventos@example.com>",
            recipients=[cliente_email]
        )
        
        # ... (Corpo do e-mail HTML idêntico ao original) ...
        msg.html = f"""
            <h2 style="font-family: Arial, sans-serif; color: #333;">Olá, {cliente_nome}!</h2>
            <p style="font-family: Arial, sans-serif; color: #555;">Este é um <strong>reenvio</strong> do orçamento para o seu evento <strong>{nome_evento}</strong>, que ocorrerá em <strong>{data_formatada}</strong>. Por favor, revise e aprove abaixo.</p>

            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <thead style="background-color: #f8f9fa;">
            <tr>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Produto/Kits</th>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Valor Unitário</th>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Quantidade</th>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Valor Total</th>
            </tr>
            </thead>
            <tbody>
                {itens_detalhados_email}
            </tbody>
            </table>

            <hr style="border-top: 2px solid #ddd; margin-top: 20px;">

            <h3 style="font-family: Arial, sans-serif; color: #333;">Resumo do Orçamento</h3>
            <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 10px; font-family: Arial, sans-serif; color: #333;">Valor Total dos Itens:</td>
                <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333;">R$ {valor_total_itens:.2f}</td>
            </tr>
            <tr>
                <td style="padding: 10px; font-family: Arial, sans-serif; color: #333;">Mão de Obra:</td>
                <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333;">R$ {mao_de_obra:.2f}</td>
            </tr>
            <tr>
            <td style="padding: 10px; font-family: Arial, sans-serif; color: #333;">Frete:</td>
            <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333;">R$ {frete:.2f}</td>
        </tr>
        <tr style="border-top: 2px solid #ddd;">
            <td style="padding: 10px; font-family: Arial, sans-serif; color: #333; font-weight: bold;">Total Geral:</td>
            <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333; font-weight: bold;">R$ {valor_total:.2f}</td>
        </tr>
        </table>

        <div style="margin-top: 30px; text-align: center;">
            <a href="{link_aprovacao}" style="background-color: #28a745; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-size: 16px; font-family: Arial, sans-serif; font-weight: bold;">Aprovar Orçamento</a>
        </div>

        <p style="font-family: Arial, sans-serif; color: #555; margin-top: 20px;">Caso tenha alguma dúvida, não hesite em entrar em contato conosco. Aguardamos sua aprovação para seguir com o processo.</p>

        <p style="font-family: Arial, sans-serif; color: #555;">Atenciosamente,</p>
        <p style="font-family: Arial, sans-serif; color: #555;">Equipe de Gestão de Eventos</p>
        """

        mail.send(msg)
        flash(f"E-mail de orçamento reenviado com sucesso para {cliente_email}!", 'success')

    except Exception as e:
        flash(f"Erro ao reenviar o e-mail do orçamento {orcamento_id}: {e}", 'error')
    finally:
        cursor.close()
    
    return redirect(url_for('orcamento_eventos'))

# Rota para Visualizar Orçamento
@app.route("/ver_orcamento/<int:orcamento_id>")
def ver_orcamento(orcamento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("orcamento_eventos"))

    cursor = db.cursor(dictionary=True)
    try:
        # Busca detalhes do orçamento
        cursor.execute("""
            SELECT 
                o.*, 
                c.nome AS cliente_nome, c.email AS cliente_email, c.telefone AS cliente_telefone
            FROM orcamentos o
            JOIN clientes c ON o.cliente_id = c.id
            WHERE o.id = %s
        """, (orcamento_id,))
        orcamento = cursor.fetchone()

        if not orcamento:
            flash("Orçamento não encontrado.", "error")
            return redirect(url_for("orcamento_eventos"))

        # Deserializa os itens
        itens_selecionados = json.loads(orcamento['itens_json'])
        itens_detalhados = []
        valor_total_itens = Decimal(0)
        
        # Busca detalhes adicionais para os itens
        for item in itens_selecionados:
            item_id = item['id']
            item_tipo = item['tipo']
            quantidade = item['quantidade']
            
            nome = ""
            valor_unitario = Decimal(0)

            if item_tipo == 'produto':
                cursor.execute("SELECT nome, preco_repasse FROM estoque WHERE id = %s", (item_id,))
                material_db = cursor.fetchone()
                if material_db:
                    nome = material_db['nome']
                    valor_unitario = Decimal(material_db['preco_repasse'])
            elif item_tipo == 'kit':
                cursor.execute("SELECT nome, valor FROM kits WHERE id = %s", (item_id,))
                material_db = cursor.fetchone()
                if material_db:
                    nome = material_db['nome']
                    valor_unitario = Decimal(material_db['valor'])

            valor_total_item = valor_unitario * quantidade
            valor_total_itens += valor_total_item

            itens_detalhados.append({
                'nome': nome or f"ITEM ID {item_id} ({item_tipo.upper()}) (Inválido)",
                'quantidade': quantidade,
                'valor_unitario': valor_unitario,
                'valor_total_item': valor_total_item,
                'tipo': item_tipo
            })

        # Formatar datas para exibição
        orcamento['data_evento_str'] = orcamento['data_evento'].strftime('%d/%m/%Y às %H:%M')
        if orcamento['recolhimento_evento']:
             orcamento['recolhimento_evento_str'] = orcamento['recolhimento_evento'].strftime('%d/%m/%Y às %H:%M')
        else:
             orcamento['recolhimento_evento_str'] = "Não Definido"

    except Exception as e:
        flash(f"Erro ao carregar os detalhes do orçamento: {e}", 'error')
        return redirect(url_for("orcamento_eventos"))
    finally:
        cursor.close()

    return render_template("ver_orcamento.html", orcamento=orcamento, itens_detalhados=itens_detalhados, valor_total_itens=valor_total_itens)




@app.route("/ver_evento/<int:evento_id>")
def ver_evento(evento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("controle_eventos"))

    cursor = db.cursor(dictionary=True)
    
    # Busca detalhes do evento, incluindo o status de pagamento
    cursor.execute("""
        SELECT 
            e.id, e.nome_evento, e.data_evento, e.recolhimento_evento, e.observacoes,
            c.nome AS cliente_nome, e.status, e.valor_total, e.status_pagamento, e.valor_pago,
            e.mao_de_obra, e.frete
        FROM eventos e 
        JOIN clientes c ON e.cliente_id = c.id 
        WHERE e.id = %s
    """, (evento_id,))
    evento = cursor.fetchone()
    
    if not evento:
        flash("Evento não encontrado.", 'error')
        return redirect(url_for("controle_eventos"))
    
    # Busca os itens associados ao evento
    cursor.execute("""
        SELECT 
            m.material_id, m.kit_id, m.quantidade, 
            IFNULL(est.nome, k.nome) AS nome_material, 
            IFNULL(est.preco_repasse, k.valor) AS valor_unitario
        FROM montagem_materiais m
        LEFT JOIN estoque est ON m.material_id = est.id
        LEFT JOIN kits k ON m.kit_id = k.id
        WHERE m.evento_id = %s
    """, (evento_id,))
    itens_evento = cursor.fetchall()
    
    # Calcular o valor total dos itens
    valor_total_itens = sum([item['valor_unitario'] * item['quantidade'] for item in itens_evento])
    
    cursor.close()
    
    return render_template("ver_evento.html", 
                           evento=evento, 
                           itens_evento=itens_evento, 
                           valor_total_itens=valor_total_itens)




@app.route("/aprovar_orcamento/<token>")
def aprovar_orcamento(token):
    db = get_db()
    if db is None:
        return "Erro de banco de dados.", 500
    
    cursor = db.cursor(dictionary=True)
    try:
        # 1. Buscar o orçamento pendente
        cursor.execute("SELECT * FROM orcamentos WHERE token = %s AND status = 'pendente'", (token,))
        orcamento = cursor.fetchone()
        if not orcamento:
            return "Orçamento inválido, já aprovado ou não encontrado.", 404

        # 2. Verificar a disponibilidade de estoque para os itens
        itens_selecionados = json.loads(orcamento['itens_json'])
        for item in itens_selecionados:
            if item['tipo'] == 'produto':
                cursor.execute("SELECT nome, quantidade_estoque FROM estoque WHERE id = %s", (item['id'],))
                produto_db = cursor.fetchone()
                if not produto_db or item['quantidade'] > produto_db['quantidade_estoque']:
                    # Corrigido o erro de referenciar orcamento_id na linha 110. O correto é orcamento['id']
                    flash(f"Não foi possível aprovar: Estoque do produto '{produto_db['nome']}' se tornou insuficiente.", 'error')
                    return redirect(url_for('index'))
            elif item['tipo'] == 'kit':
                cursor.execute("SELECT nome, status FROM kits WHERE id = %s", (item['id'],))
                kit_db = cursor.fetchone()
                if not kit_db or kit_db['status'] != 'disponivel':
                    flash(f"Não foi possível aprovar: O kit '{kit_db['nome']}' não está mais disponível.", 'error')
                    return redirect(url_for('index'))

        # 3. Criar o evento oficial e incluir os valores de mão de obra, frete E O ID DO ORÇAMENTO (AJUSTADO AQUI)
        cursor.execute(
            "INSERT INTO eventos (nome_evento, cliente_id, tipo_evento, data_evento, recolhimento_evento, observacoes, valor_total, mao_de_obra, frete, orcamento_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                orcamento['nome_evento'], orcamento['cliente_id'], orcamento['tipo_evento'], 
                orcamento['data_evento'], orcamento['data_evento'], orcamento['observacoes'], 
                orcamento['valor_total'], orcamento['mao_de_obra'], orcamento['frete'], orcamento['id'] # <-- orcamento['id'] é o ID do orçamento aprovado
            )
        )
        evento_id = cursor.lastrowid

        # 4. Inserir os itens do orçamento como materiais do evento
        for item in itens_selecionados:
            material_id = item['id'] if item['tipo'] == 'produto' else None
            kit_id = item['id'] if item['tipo'] == 'kit' else None
            cursor.execute(
                "INSERT INTO montagem_materiais (evento_id, material_id, kit_id, quantidade) "
                "VALUES (%s, %s, %s, %s)",
                (evento_id, material_id, kit_id, item['quantidade'])
            )
            if item['tipo'] == 'produto':
                cursor.execute("UPDATE estoque SET quantidade_estoque = quantidade_estoque - %s WHERE id = %s", (item['quantidade'], item['id']))
            elif item['tipo'] == 'kit':
                cursor.execute("UPDATE kits SET status = 'em_uso' WHERE id = %s", (item['id'],))

        # 5. Atualizar o status do orçamento para aprovado
        cursor.execute("UPDATE orcamentos SET status = 'aprovado' WHERE id = %s", (orcamento['id'],))
        
        db.commit()

    except Exception as e:
        db.rollback()
        flash(f"Ocorreu um erro crítico durante a aprovação: {e}", "error")
        return redirect(url_for('index'))
    finally:
        cursor.close()

    # Redirecionar para a tela de "Orçamento Aprovado"
    return redirect(url_for('orcamento_aprovado', evento_id=evento_id))


@app.route("/orcamento_aprovado")
def orcamento_aprovado():
    return render_template("orcamento_aprovado.html")






# =========================
# KITS
# =========================
@app.route("/kits", methods=["GET", "POST"])
def kits():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("index"))

    if request.method == "POST":
        nome_kit = (request.form.get("nome_kit") or "").strip()
        valor_kit = request.form.get("valor_kit")
        foto = request.files.get("foto_kit")
        
        itens_selecionados = []
        i = 0
        while True:
            item_id = request.form.get(f'itens[{i}][id]')
            if item_id is None: break
            try:
                itens_selecionados.append({
                    'id': int(item_id),
                    'quantidade': int(request.form.get(f'itens[{i}][quantidade]'))
                })
            except (ValueError, TypeError):
                flash("Dados de itens inválidos recebidos.", "error")
                return redirect(url_for('kits'))
            i += 1

        if not nome_kit or not valor_kit or not itens_selecionados:
            flash("Nome, valor e ao menos um item são obrigatórios.", "error")
            return redirect(url_for("kits"))

        cursor = None
        foto_path = None
        try:
            cursor = db.cursor(dictionary=True)
            # Validação de estoque dos componentes
            for item in itens_selecionados:
                cursor.execute("SELECT nome, quantidade_estoque FROM estoque WHERE id = %s", (item['id'],))
                produto_db = cursor.fetchone()
                if not produto_db or item['quantidade'] > produto_db['quantidade_estoque']:
                    flash(f"Estoque insuficiente para o item '{produto_db['nome']}'. Solicitado: {item['quantidade']}, Disponível: {produto_db['quantidade_estoque']}.", 'error')
                    return redirect(url_for('kits'))
            
            # Salva imagem
            if foto and foto.filename:
                foto_path = save_image(foto, subdir="kits")

            # Cria o kit com status 'disponivel'
            cursor.execute("INSERT INTO kits (nome, valor, foto_path, status) VALUES (%s, %s, %s, 'disponivel')", (nome_kit, valor_kit, foto_path))
            kit_id = cursor.lastrowid

            # Vincula itens e DÁ BAIXA no estoque dos componentes
            for item in itens_selecionados:
                cursor.execute("INSERT INTO kit_itens (kit_id, material_id, quantidade) VALUES (%s, %s, %s)", (kit_id, item['id'], item['quantidade']))
                cursor.execute("UPDATE estoque SET quantidade_estoque = quantidade_estoque - %s WHERE id = %s", (item['quantidade'], item['id']))
            
            db.commit()
            flash("Kit cadastrado com sucesso! Itens foram deduzidos do estoque.", "success")
        except Exception as e:
            db.rollback()
            if foto_path: remove_file_if_exists(foto_path)
            flash(f"Ocorreu um erro ao salvar o kit: {e}", "error")
        finally:
            if cursor: cursor.close()
        return redirect(url_for("kits"))

    # GET
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, tipo_material, unidade_medida, quantidade_estoque FROM estoque ORDER BY nome")
    todos_materiais = cursor.fetchall()
    
    # Busca kits e seu status
    cursor.execute("SELECT id, nome, valor, created_at, foto_path, status FROM kits ORDER BY created_at DESC")
    kits_list = cursor.fetchall()

    kits_itens_map = {}
    if kits_list:
        kit_ids = [k["id"] for k in kits_list]
        in_clause = ",".join(["%s"] * len(kit_ids))
        cursor.execute(f"SELECT ki.kit_id, e.nome, ki.quantidade FROM kit_itens ki JOIN estoque e ON e.id = ki.material_id WHERE ki.kit_id IN ({in_clause})", tuple(kit_ids))
        for row in cursor.fetchall():
            kits_itens_map.setdefault(row["kit_id"], []).append(f"{row['nome']} ({row['quantidade']}x)")
    cursor.close()
    
    return render_template("kit_cadastro.html", todos_materiais=todos_materiais, kits_list=kits_list, kits_itens_map=kits_itens_map)

@app.route("/deletar_kit/<int:kit_id>", methods=["POST"])
def deletar_kit(kit_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        # Verifica se o kit não está em uso
        cursor.execute("SELECT status, foto_path FROM kits WHERE id = %s", (kit_id,))
        kit = cursor.fetchone()
        if not kit:
            flash("Kit não encontrado.", "error")
            return redirect(url_for("kits"))
        
        if kit['status'] == 'em_uso':
            flash("Não é possível excluir um kit que está atualmente em uso em um evento.", "error")
            return redirect(url_for("kits"))

        # Busca os itens do kit para devolver ao estoque
        cursor.execute("SELECT material_id, quantidade FROM kit_itens WHERE kit_id = %s", (kit_id,))
        itens_do_kit = cursor.fetchall()
        for item in itens_do_kit:
            cursor.execute("UPDATE estoque SET quantidade_estoque = quantidade_estoque + %s WHERE id = %s", (item['quantidade'], item['material_id']))

        # Deleta o kit e seus itens
        cursor.execute("DELETE FROM kit_itens WHERE kit_id = %s", (kit_id,))
        cursor.execute("DELETE FROM kits WHERE id = %s", (kit_id,))
        db.commit()

        if kit['foto_path']: remove_file_if_exists(kit['foto_path'])
        flash("Kit excluído com sucesso! Itens retornaram ao estoque.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Erro ao excluir kit: {e}", "error")
    finally:
        cursor.close()
    return redirect(url_for("kits"))

# ========================
# CONSULTA ESTOQUE (lista/filtra)
# ========================
@app.route("/consulta_estoque")
def consulta_estoque():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("consulta_estoque"))

    cursor = db.cursor(dictionary=True)
    # Inclui quantidade_venda; foto_path pode ser útil na listagem futura
    cursor.execute("""
        SELECT 
            id, 
            nome, 
            tipo_material, 
            unidade_medida, 
            COALESCE(quantidade_venda, 0) AS quantidade_venda,
            quantidade_estoque, 
            preco_compra, 
            preco_repasse,
            foto_path
        FROM estoque
        ORDER BY id DESC
    """)
    materiais = cursor.fetchall()
    cursor.close()
    
    return render_template("consulta_estoque.html", materiais=materiais)

@app.route("/deletar_material/<int:material_id>", methods=["POST"])
def deletar_material(material_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        msg = "Erro ao conectar ao banco de dados."
        flash(msg, 'error')
        return redirect(url_for("consulta_estoque", **{"err": msg}))

    try:
        # Busca foto_path para apagar caso delete
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT foto_path, nome FROM estoque WHERE id = %s", (material_id,))
        row = cur.fetchone()
        foto_path = row["foto_path"] if row else None
        nome_material = row["nome"] if row else None
        cur.close()

        # Buscar se o material tem algum valor de despesa no fluxo de caixa
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT valor FROM fluxo_caixa
            WHERE descricao LIKE %s AND tipo = 'Despesa'""", (f"%{nome_material}%",))
        fluxo_despesa = cursor.fetchone()
        
        # Se encontrar a despesa no fluxo de caixa, remover
        if fluxo_despesa:
            cursor.execute("""
                DELETE FROM fluxo_caixa
                WHERE descricao LIKE %s AND tipo = 'Despesa'""", (f"%{nome_material}%",))
            db.commit()

        # Agora exclui o material do estoque
        cursor.execute("DELETE FROM estoque WHERE id = %s", (material_id,))
        db.commit()
        cursor.close()

        # Remove arquivo de foto se existir
        if foto_path:
            remove_file_if_exists(foto_path)

        flash('Produto excluído com sucesso, despesa removida!', 'success')
        return redirect(url_for('consulta_estoque', **{"ok": "1"}))
    except mysql_errors.IntegrityError as e:
        err_no = getattr(e, "errno", None)
        if err_no == 1451:
            msg = 'Não foi possível excluir: o produto está vinculado a um Kit ou a uma Montagem de Evento.'
        else:
            msg = f'Erro de integridade ao excluir o produto (código {err_no}).'
        flash(msg, 'error')
        return redirect(url_for('consulta_estoque', **{"err": msg}))
    except Exception as e:
        msg = f'Ocorreu um erro ao excluir o produto: {e}'
        flash(msg, 'error')
        return redirect(url_for('consulta_estoque', **{"err": msg}))



# ========================
# CLIENTES
# ========================
@app.route("/cadastro_cliente", methods=["GET", "POST"])
def cadastro_cliente():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", "error")
        return redirect(url_for("cadastro_cliente"))

    if request.method == "POST":
        nome       = (request.form.get("nome") or "").strip()
        telefone   = only_digits(request.form.get("telefone"))
        email      = (request.form.get("email") or "").strip().lower()
        cpf        = only_digits(request.form.get("cpf"))
        cep        = only_digits(request.form.get("cep"))
        endereco   = (request.form.get("endereco") or "").strip()
        bairro     = (request.form.get("bairro") or "").strip()
        cidade     = (request.form.get("cidade") or "").strip()
        uf         = (request.form.get("uf") or "").strip().upper()[:2]
        numero     = (request.form.get("numero") or "").strip()
        complemento= (request.form.get("complemento") or "").strip()

        if not nome:
            flash("Informe o nome do cliente.", "error"); return redirect(url_for("cadastro_cliente"))
        if not email:
            flash("Informe um e-mail válido.", "error"); return redirect(url_for("cadastro_cliente"))
        if len(cpf) != 11:
            flash("CPF inválido. Informe 11 dígitos (somente números).", "error"); return redirect(url_for("cadastro_cliente"))
        if len(cep) != 8:
            flash("CEP inválido. Informe 8 dígitos (somente números).", "error"); return redirect(url_for("cadastro_cliente"))
        if len(uf) != 2:
            flash("UF inválida. Informe 2 letras (ex.: PE, SP).", "error"); return redirect(url_for("cadastro_cliente"))

        cursor = None
        try:
            cursor = db.cursor()
            cursor.execute(
                """
                INSERT INTO clientes 
                    (nome, telefone, email, cpf, cep, endereco, bairro, cidade, uf, numero, complemento)
                VALUES 
                    (%s,   %s,       %s,    %s,  %s,  %s,       %s,     %s,     %s, %s,     %s)
                """,
                (nome, telefone, email, cpf, cep, endereco, bairro, cidade, uf, numero, complemento)
            )
            db.commit()
            flash("Cliente cadastrado com sucesso!", "success")
        except mysql.connector.IntegrityError as e:
            if getattr(e, "errno", None) == 1062:
                msg = str(e).lower()
                if "cpf" in msg:
                    flash("CPF já cadastrado. Informe um CPF diferente.", "error")
                elif "email" in msg:
                    flash("E-mail já cadastrado. Informe um e-mail diferente.", "error")
                else:
                    flash("Registro duplicado. Verifique os dados informados.", "error")
            else:
                flash(f"Erro de integridade ao salvar o cliente: {e}", "error")
        except Exception as e:
            db.rollback()
            flash(f"Ocorreu um erro: {e}", "error")
        finally:
            try:
                if cursor:
                    cursor.close()
            except:
                pass
        return redirect(url_for("cadastro_cliente"))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM clientes ORDER BY id DESC")
    clientes = cursor.fetchall()
    cursor.close()
    return render_template("cadastro_cliente.html", clientes=clientes)

@app.route("/deletar_cliente/<int:cliente_id>", methods=["POST"])
def deletar_cliente(cliente_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        msg = "Erro ao conectar ao banco de dados."
        flash(msg, "error")
        return redirect(url_for("cadastro_cliente", err=msg))

    try:
        cur = db.cursor()
        cur.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))
        db.commit()
        cur.close()
        flash("Cliente excluído com sucesso!", "success")
        return redirect(url_for("cadastro_cliente", ok=1))
    except mysql_errors.IntegrityError:
        msg = "Não foi possível excluir: este cliente está vinculado a outros registros (ex.: eventos)."
        flash(msg, "error")
        return redirect(url_for("cadastro_cliente", err=msg))
    except Exception as e:
        msg = f"Ocorreu um erro ao excluir o cliente: {e}"
        flash(msg, "error")
        return redirect(url_for("cadastro_cliente", err=msg))



# ========================
# CEP
# ========================
@app.route("/consulta_cep/<cep_number>", methods=["GET"])
@app.route("/consulta_cep", methods=["GET"])
def consulta_cep(cep_number=None):
    if not cep_number:
        cep_number = request.args.get("cep", "")
    cep_number = re.sub(r"\D", "", str(cep_number or ""))
    if len(cep_number) != 8:
        return jsonify({"erro": True, "mensagem": "CEP inválido. Deve conter 8 dígitos."}), 400
    try:
        url = f"https://viacep.com.br/ws/{cep_number}/json/"
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        dados_cep = response.json()
        if dados_cep.get("erro") is True:
            return jsonify({"erro": True, "mensagem": "CEP não encontrado."}), 200
        return jsonify({
            "erro": False,
            "cep": dados_cep.get("cep", "").replace("-", ""),
            "logradouro": dados_cep.get("logradouro", ""), 
            "complemento": dados_cep.get("complemento", ""),
            "bairro": dados_cep.get("bairro", ""), 
            "localidade": dados_cep.get("localidade", ""),
            "uf": dados_cep.get("uf", "")
        }), 200
    except requests.exceptions.Timeout:
        return jsonify({"erro": True, "mensagem": "Timeout ao consultar serviço de CEP."}), 504
    except requests.exceptions.RequestException:
        return jsonify({"erro": True, "mensagem": "Erro ao comunicar com serviço de CEP."}), 500
    except Exception:
        return jsonify({"erro": True, "mensagem": "Erro interno do servidor."}), 500

# ========================
# Tabela de preços
# ========================
@app.route("/tabela_precos", methods=["GET", "POST"])
def tabela_precos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("tabela_precos"))
    
    if request.method == "POST":
        nome = request.form.get("nome")
        tipo = request.form.get("tipo")
        preco = request.form.get("preco")
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO precos (nome, tipo, preco) VALUES (%s, %s, %s)",
                           (nome, tipo, preco))
            db.commit()
            cursor.close()
            flash("Preço cadastrado com sucesso!", 'success')
        except mysql.connector.IntegrityError:
            flash("Item com este nome já existe. Por favor, escolha outro.", 'error')
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", 'error')
            
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM precos")
    precos = cursor.fetchall()
    cursor.close()
    return render_template("tabela_precos.html", precos=precos)

# ========================
# Eventos
# ========================
# No seu arquivo app.py, substitua a função /eventos por esta:




@app.route("/eventos", methods=["GET", "POST"])
def eventos():
    if not session.get("logged_in"): 
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("index"))
    
    if request.method == "POST":
        cursor = None
        try:
            # Dados básicos do formulário
            nome_evento = request.form.get("nome_evento")
            cliente_id = request.form.get("cliente_id")
            tipo_evento = request.form.get("tipo_evento")
            data_evento = request.form.get("data_evento")
            recolhimento_evento = request.form.get("recolhimento_evento")
            observacoes = request.form.get("observacoes")
            mao_de_obra = request.form.get("mao_de_obra") 
            frete = request.form.get("frete") 

            # ✅ NOVO CAMPO: orcamento_id. Assumimos que ele vem de um campo oculto
            # no formulário de aprovação/conversão do orçamento.
            orcamento_id = request.form.get("orcamento_id") 

            # Verificar se Mão de Obra e Frete foram fornecidos e convertê-los para Decimal
            mao_de_obra = Decimal(mao_de_obra) if mao_de_obra else Decimal(0)
            frete = Decimal(frete) if frete else Decimal(0)
            
            # Processar itens
            itens_selecionados = []
            i = 0
            while True:
                item_id = request.form.get(f'itens[{i}][id]')
                if item_id is None: break
                itens_selecionados.append({
                    'id': int(item_id),
                    'tipo': request.form.get(f'itens[{i}][tipo]'),
                    'quantidade': int(request.form.get(f'itens[{i}][quantidade]'))
                })
                i += 1

            if not nome_evento or not cliente_id or not data_evento or not itens_selecionados:
                flash("Nome do evento, cliente, data e ao menos um item são obrigatórios.", 'error')
                return redirect(url_for('eventos'))

            cursor = db.cursor(dictionary=True)

            # --- VALIDAÇÃO DE ESTOQUE E DISPONIBILIDADE DE KITS (Lógica mantida) ---
            for item in itens_selecionados:
                if item['tipo'] == 'produto':
                    cursor.execute("SELECT nome, quantidade_estoque FROM estoque WHERE id = %s", (item['id'],))
                    produto_db = cursor.fetchone()
                    if not produto_db or item['quantidade'] > produto_db['quantidade_estoque']:
                        flash(f"Erro de estoque para o produto '{produto_db['nome']}'. Solicitado: {item['quantidade']}, Disponível: {produto_db['quantidade_estoque']}.", 'error')
                        return redirect(url_for('eventos'))
                
                elif item['tipo'] == 'kit':
                    cursor.execute("SELECT nome, status FROM kits WHERE id = %s", (item['id'],))
                    kit_db = cursor.fetchone()
                    if not kit_db or kit_db['status'] != 'disponivel':
                        flash(f"O kit '{kit_db['nome'] if kit_db else 'ID ' + str(item['id'])}' não está disponível para uso.", 'error')
                        return redirect(url_for('eventos'))

            # Cálculo do valor total (Lógica mantida)
            valor_total_evento = Decimal(0)
            itens_para_salvar = []
            for item in itens_selecionados:
                valor_item_unitario = Decimal(0)
                if item['tipo'] == 'produto':
                    cursor.execute("SELECT preco_repasse FROM estoque WHERE id = %s", (item['id'],))
                    produto = cursor.fetchone()
                    if produto: valor_item_unitario = Decimal(produto['preco_repasse'])
                elif item['tipo'] == 'kit':
                    cursor.execute("SELECT valor FROM kits WHERE id = %s", (item['id'],))
                    kit = cursor.fetchone()
                    if kit: valor_item_unitario = Decimal(kit['valor'])
                valor_total_evento += valor_item_unitario * item['quantidade']
                itens_para_salvar.append({**item, 'valor_item': valor_item_unitario})

            # Adicionando Mão de Obra e Frete ao valor total do evento
            valor_total_evento += mao_de_obra + frete

            # ✅ ATUALIZAÇÃO DO INSERT: Incluindo orcamento_id
            cursor.execute(
                """
                INSERT INTO eventos (nome_evento, cliente_id, tipo_evento, data_evento, recolhimento_evento, observacoes, valor_total, mao_de_obra, frete, status_pagamento, orcamento_id) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendente', %s)
                """,
                (nome_evento, cliente_id, tipo_evento, data_evento, recolhimento_evento or None, observacoes, valor_total_evento, mao_de_obra, frete, orcamento_id)
            )
            evento_id = cursor.lastrowid

            # --- LÓGICA DE BAIXA DE ESTOQUE E ATUALIZAÇÃO DE STATUS (Mantida) ---
            for item_final in itens_para_salvar:
                material_id = item_final['id'] if item_final['tipo'] == 'produto' else None
                kit_id = item_final['id'] if item_final['tipo'] == 'kit' else None
                cursor.execute(
                    "INSERT INTO montagem_materiais (evento_id, material_id, kit_id, quantidade, valor_item) VALUES (%s, %s, %s, %s, %s)",
                    (evento_id, material_id, kit_id, item_final['quantidade'], item_final['valor_item'])
                )
                
                if item_final['tipo'] == 'produto':
                    # Baixa no estoque apenas para produtos avulsos
                    cursor.execute("UPDATE estoque SET quantidade_estoque = quantidade_estoque - %s WHERE id = %s", (item_final['quantidade'], item_final['id']))
                elif item_final['tipo'] == 'kit':
                    # Para kits, apenas muda o status para 'em_uso'
                    cursor.execute("UPDATE kits SET status = 'em_uso' WHERE id = %s", (item_final['id'],))

            db.commit()
            flash("Evento cadastrado com sucesso, aguardando pagamento!", 'success')
        except Exception as e:
            if db: db.rollback()
            flash(f"Ocorreu um erro ao cadastrar o evento: {e}", 'error')
        finally:
            if cursor: cursor.close()

        return redirect(url_for('eventos'))

    # --- LÓGICA DE EXIBIÇÃO DA PÁGINA (GET) ---
    cursor = db.cursor(dictionary=True)
    
    # Busca de clientes e produtos (sem mudanças)
    cursor.execute("SELECT id, nome FROM clientes ORDER BY nome")
    clientes = cursor.fetchall()
    cursor.execute("SELECT e.id, e.nome_evento, e.data_evento, c.nome as cliente_nome, e.status, e.valor_total, e.status_pagamento FROM eventos e JOIN clientes c ON e.cliente_id = c.id ORDER BY e.data_evento DESC")
    eventos_cadastrados = cursor.fetchall() # Isso garante que o novo evento apareça na lista
    cursor.execute("SELECT id, nome, preco_repasse, quantidade_estoque FROM estoque ORDER BY nome")
    produtos = cursor.fetchall()
    
    # --- AJUSTE NA LÓGICA DE BUSCA DE KITS ---
    cursor.execute("SELECT id, nome, valor FROM kits WHERE status = 'disponivel' ORDER BY nome")
    kits_disponiveis = cursor.fetchall()
    for kit in kits_disponiveis:
        # Define que cada kit disponível representa 1 unidade em estoque
        kit['estoque_disponivel'] = 1 

    cursor.close()
    
    return render_template("eventos.html", 
                            clientes=clientes, 
                            eventos=eventos_cadastrados, 
                            produtos=produtos, 
                            kits=kits_disponiveis)


@app.route("/calendario_eventos")
def calendario_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for('index'))
    
    cursor = db.cursor(dictionary=True)
    
    # Busca TODOS os eventos com os dados necessários
    cursor.execute("""
        SELECT 
            e.nome_evento, 
            e.data_evento, 
            e.status, 
            c.nome as cliente_nome 
        FROM eventos e 
        JOIN clientes c ON e.cliente_id = c.id
    """)
    eventos = cursor.fetchall()
    cursor.close()

    return render_template("calendario_eventos.html", eventos=eventos)


@app.route("/controle_eventos")
def controle_eventos():
    # 1. Verificação de Login
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    
    # 2. Verificação de Conexão com o DB
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("index"))
        
    eventos = []
    cursor = None # Inicializa o cursor fora do try
    
    try:
        cursor = db.cursor(dictionary=True)
        # Execução da consulta dentro do bloco try
        cursor.execute("""
            SELECT 
                e.id, e.nome_evento, e.data_evento, e.recolhimento_evento, 
                e.observacoes, c.nome as cliente_nome, e.status, e.valor_total, e.status_pagamento, e.valor_pago
            FROM eventos e 
            JOIN clientes c ON e.cliente_id = c.id 
            ORDER BY e.data_evento DESC, e.id DESC
        """)
        eventos = cursor.fetchall()

    except Exception as e:
        # Tratamento de erro caso a consulta falhe
        print(f"Erro ao carregar eventos: {e}")
        flash("Erro interno ao carregar a lista de eventos.", 'error')
        # Redirecionar em caso de falha crítica na leitura
        return redirect(url_for("index")) 

    finally:
        # 3. Garante que o cursor seja fechado (CRÍTICO)
        if cursor:
            cursor.close()
        # Nota: Se o seu `get_db()` não usa o teardown do Flask, você também precisará
        # fechar a conexão db aqui (db.close()). Assumo que o Flask esteja gerenciando.
    
    # 4. Renderização
    return render_template("controle_eventos.html", eventos=eventos)





# NO SEU ARQUIVO app.py:

# =================================================================
# PASSO 1: ESTA É A NOVA FUNÇÃO PARA MOSTRAR A PÁGINA DO FORMULÁRIO
# =================================================================
@app.route("/finalizar_evento_form/<int:evento_id>", methods=["GET"])
def finalizar_evento_form(evento_id):
    """Exibe a página de confirmação para finalizar um evento."""
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("controle_eventos"))
        
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, nome_evento FROM eventos WHERE id = %s", (evento_id,))
    evento = cursor.fetchone()
    cursor.close()

    if not evento:
        flash("Evento não encontrado.", "error")
        return redirect(url_for("controle_eventos"))

    return render_template("finalizar_evento.html", evento=evento)


# =================================================================
# PASSO 2: ESTA É A FUNÇÃO ORIGINAL QUE PROCESSA O ENVIO DO FORMULÁRIO
# GARANTA QUE ELA AINDA EXISTA E ESTEJA CORRETA.
# =================================================================
@app.route("/finalizar_evento/<int:evento_id>", methods=["POST"])
def finalizar_evento(evento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    recolhimento_status = request.form.get("recolhimento_status")
    observacoes = request.form.get("observacoes")

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("controle_eventos"))
        
    cursor = db.cursor(dictionary=True)
    try:
        # Busca todos os itens do evento (produtos e kits)
        cursor.execute("SELECT material_id, kit_id, quantidade FROM montagem_materiais WHERE evento_id = %s", (evento_id,))
        itens_do_evento = cursor.fetchall()
        
        if recolhimento_status == "Total":
            for item in itens_do_evento:
                # Se for um material de aluguel avulso, devolve ao estoque
                if item['material_id']:
                    cursor.execute("SELECT tipo_material FROM estoque WHERE id = %s", (item['material_id'],))
                    produto = cursor.fetchone()
                    if produto and produto['tipo_material'] == 'aluguel':
                        cursor.execute("UPDATE estoque SET quantidade_estoque = quantidade_estoque + %s WHERE id = %s", (item['quantidade'], item['material_id']))
                
                # Se for um kit, muda o status para 'disponivel'
                elif item['kit_id']:
                    cursor.execute("UPDATE kits SET status = 'disponivel' WHERE id = %s", (item['kit_id'],))

            cursor.execute("UPDATE eventos SET status = 'Finalizado', observacoes = %s WHERE id = %s", ("Recolhimento total.", evento_id))
            flash("Evento finalizado! Itens de aluguel e kits retornaram ao estado disponível.", 'success')

        elif recolhimento_status == "Parcial":
            # Para finalização parcial, também liberamos os kits
            for item in itens_do_evento:
                if item['kit_id']:
                    cursor.execute("UPDATE kits SET status = 'disponivel' WHERE id = %s", (item['kit_id'],))
            
            cursor.execute("UPDATE eventos SET status = 'Finalização Parcial', observacoes = %s WHERE id = %s", (observacoes, evento_id))
            flash("Status do evento atualizado. Kits foram liberados, mas itens avariados não retornaram ao estoque.", 'warning')

        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"Ocorreu um erro ao finalizar o evento: {e}", 'error')
    finally:
        cursor.close()
        
    return redirect(url_for("controle_eventos"))




def registrar_log_atividade(db, tipo, id_referencia, descricao):
    """
    Insere um novo registro de log genérico na tabela log_atividades.
    Usa uma transação isolada e usa a coluna 'data_log'.
    """
    cursor = db.cursor() 
    try:
        # Insere a descrição e tipo fornecidos, confiando no DEFAULT CURRENT_TIMESTAMP do MySQL.
        cursor.execute("""
            INSERT INTO log_atividades (tipo, id_referencia, descricao)
            VALUES (%s, %s, %s)
        """, (tipo, id_referencia, descricao))
        
        db.commit() # Confirma a inserção do log separadamente
        print(f"DEBUG: Log registrado com sucesso para Tipo: {tipo}, ID: {id_referencia}")
        
    except Exception as e:
        # Tenta dar rollback apenas na transação do log
        try:
            db.rollback()
        except:
            pass
            
        # Imprime o erro crítico no console para depuração
        print("-" * 50)
        print(f"ERRO CRÍTICO no SQL ao registrar log para {tipo} ID {id_referencia}: {e}")
        print("-" * 50)
    finally:
        cursor.close()

# ----------------------------------------------------------------------
# ROTA DE ORÇAMENTO 
# ----------------------------------------------------------------------


@app.route("/orcamento_eventos", methods=["GET", "POST"])
def orcamento_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("index"))

    if request.method == "POST":
        cursor = db.cursor(dictionary=True)
        try:
            # Dados do formulário
            nome_evento = request.form.get("nome_evento")
            cliente_id = request.form.get("cliente_id")
            tipo_evento = request.form.get("tipo_evento")
            data_evento = request.form.get("data_evento")
            data_recolhimento = request.form.get("data_recolhimento")
            observacoes = request.form.get("observacoes")
            
            # Captura dos valores de Mão de Obra e Frete e converte para Decimal
            mao_de_obra = Decimal(request.form.get("mao_de_obra", 0))
            frete = Decimal(request.form.get("frete", 0))

            # Obter informações do cliente
            cursor.execute("SELECT nome, email FROM clientes WHERE id = %s", (cliente_id,))
            cliente = cursor.fetchone()
            if not cliente or not cliente['email']:
                flash("Cliente não encontrado ou sem e-mail cadastrado.", "error")
                return redirect(url_for('orcamento_eventos'))
            cliente_email = cliente['email']
            cliente_nome = cliente['nome']

            # Itens selecionados
            itens_selecionados = []
            i = 0
            while True:
                item_id = request.form.get(f'itens[{i}][id]')
                if item_id is None: break
                itens_selecionados.append({
                    'id': int(item_id),
                    'tipo': request.form.get(f'itens[{i}][tipo]'),
                    'quantidade': int(request.form.get(f'itens[{i}][quantidade]'))
                })
                i += 1

            if not all([nome_evento, cliente_id, data_evento, data_recolhimento, itens_selecionados]):
                flash("Todos os campos principais são obrigatórios.", "error")
                return redirect(url_for('orcamento_eventos'))

            # Calcular o valor total incluindo mão de obra e frete
            valor_total = Decimal(0)
            valor_total_itens = Decimal(0)  # Para calcular o valor total dos itens
            itens_detalhados_email = ""
            for item in itens_selecionados:
                if item['tipo'] == 'produto':
                    cursor.execute("SELECT nome, quantidade_estoque, preco_repasse FROM estoque WHERE id = %s", (item['id'],))
                    produto_db = cursor.fetchone()
                    if not produto_db or item['quantidade'] > produto_db['quantidade_estoque']:
                        flash(f"Estoque insuficiente para o produto '{produto_db['nome']}'.", 'error')
                        return redirect(url_for('orcamento_eventos'))
                    valor_unitario = Decimal(produto_db['preco_repasse'])
                    valor_total_item = valor_unitario * item['quantidade']
                    valor_total_itens += valor_total_item
                    valor_total += valor_total_item
                    itens_detalhados_email += f"""
                        <tr>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">{produto_db['nome']}</td>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">R$ {valor_unitario:.2f}</td>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">{item['quantidade']}</td>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">R$ {valor_total_item:.2f}</td>
                        </tr>
                    """
                elif item['tipo'] == 'kit':
                    cursor.execute("SELECT nome, status, valor FROM kits WHERE id = %s", (item['id'],))
                    kit_db = cursor.fetchone()
                    if not kit_db or kit_db['status'] != 'disponivel':
                        flash(f"O kit '{kit_db['nome']}' não está mais disponível.", 'error')
                        return redirect(url_for('orcamento_eventos'))
                    valor_unitario = Decimal(kit_db['valor'])
                    valor_total_item = valor_unitario * item['quantidade']
                    valor_total_itens += valor_total_item
                    valor_total += valor_total_item
                    itens_detalhados_email += f"""
                        <tr>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">{kit_db['nome']}</td>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">R$ {valor_unitario:.2f}</td>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">{item['quantidade']}</td>
                            <td style="padding: 10px; font-family: Arial, sans-serif; color: #555; border: 1px solid #ddd;">R$ {valor_total_item:.2f}</td>
                        </tr>
                    """

            # Adicionando o valor de mão de obra e frete ao total
            valor_total += mao_de_obra + frete

            # Geração do token
            token = str(uuid4())
            cursor.execute(
                "INSERT INTO orcamentos (nome_evento, cliente_id, tipo_evento, data_evento, recolhimento_evento, valor_total, observacoes, mao_de_obra, frete, itens_json, token, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendente')",  # Status 'Pendente' para o orçamento
                (nome_evento, cliente_id, tipo_evento, data_evento, data_recolhimento, valor_total, observacoes, mao_de_obra, frete, json.dumps(itens_selecionados), token)
            )
            db.commit()

            # Link para aprovação do orçamento
            link_aprovacao = url_for('aprovar_orcamento', token=token, _external=True)

            # Configuração do e-mail com o nome da empresa como remetente
            msg = Message(
                subject=f"Orçamento para seu evento: {nome_evento}",
                sender="GESTÃO DE EVENTOS <gestao.eventos@example.com>",  # Nome da empresa como remetente
                recipients=[cliente_email]
            )

            # Formatação da data para o corpo do e-mail
            data_formatada = datetime.strptime(data_evento, '%Y-%m-%dT%H:%M').strftime('%d/%m/%Y às %H:%M')
            
            # Corpo do e-mail com tabela de detalhes
            msg.html = f"""
            <h2 style="font-family: Arial, sans-serif; color: #333;">Olá, {cliente_nome}!</h2>
            <p style="font-family: Arial, sans-serif; color: #555;">Segue abaixo o orçamento para o seu evento <strong>{nome_evento}</strong>, que ocorrerá em <strong>{data_formatada}</strong>.</p>

            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
             <thead style="background-color: #f8f9fa;">
            <tr>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Produto/Kits</th>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Valor Unitário</th>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Quantidade</th>
                <th style="padding: 10px; text-align: left; font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd;">Valor Total</th>
            </tr>
            </thead>
            <tbody>
                  {itens_detalhados_email}
            </tbody>
            </table>

             <hr style="border-top: 2px solid #ddd; margin-top: 20px;">

             <h3 style="font-family: Arial, sans-serif; color: #333;">Resumo do Orçamento</h3>
            <table style="width: 100%; border-collapse: collapse;">
            <tr>
                 <td style="padding: 10px; font-family: Arial, sans-serif; color: #333;">Valor Total dos Itens:</td>
                 <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333;">R$ {valor_total_itens:.2f}</td>
             </tr>
             <tr>
                 <td style="padding: 10px; font-family: Arial, sans-serif; color: #333;">Mão de Obra:</td>
                 <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333;">R$ {mao_de_obra:.2f}</td>
                </tr>
             <tr>
            <td style="padding: 10px; font-family: Arial, sans-serif; color: #333;">Frete:</td>
            <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333;">R$ {frete:.2f}</td>
        </tr>
        <tr style="border-top: 2px solid #ddd;">
            <td style="padding: 10px; font-family: Arial, sans-serif; color: #333; font-weight: bold;">Total Geral:</td>
            <td style="padding: 10px; text-align: right; font-family: Arial, sans-serif; color: #333; font-weight: bold;">R$ {valor_total:.2f}</td>
        </tr>
    </table>

    <div style="margin-top: 30px; text-align: center;">
        <a href="{link_aprovacao}" style="background-color: #28a745; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-size: 16px; font-family: Arial, sans-serif; font-weight: bold;">Aprovar Orçamento</a>
    </div>

    <p style="font-family: Arial, sans-serif; color: #555; margin-top: 20px;">Caso tenha alguma dúvida, não hesite em entrar em contato conosco. Aguardamos sua aprovação para seguir com o processo.</p>

    <p style="font-family: Arial, sans-serif; color: #555;">Atenciosamente,</p>
    <p style="font-family: Arial, sans-serif; color: #555;">Equipe de Gestão de Eventos</p>
"""

            # Envio do e-mail
            mail.send(msg)
            flash(f"Orçamento salvo e e-mail enviado para {cliente_email}!", 'success')

        except Exception as e:
            db.rollback()
            flash(f"Ocorreu um erro ao criar o orçamento: {e}", 'error')
        finally:
            if cursor: cursor.close()
        return redirect(url_for('orcamento_eventos'))

    # GET
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, nome FROM clientes ORDER BY nome")
    clientes = cursor.fetchall()
    cursor.execute("SELECT id, nome, quantidade_estoque, preco_repasse, tipo_material FROM estoque ORDER BY nome")
    produtos = cursor.fetchall()
    cursor.execute("SELECT id, nome, valor, status FROM kits WHERE status = 'disponivel' ORDER BY nome")
    kits = cursor.fetchall()
    for kit in kits:
        kit['estoque_disponivel'] = 1

    # Consulta para carregar TODOS os orçamentos (pendentes, aprovados, etc.)
    # O status 'aprovado' é importante para a lista de acompanhamento.
    cursor.execute("SELECT o.*, c.nome as cliente_nome FROM orcamentos o JOIN clientes c ON o.cliente_id = c.id ORDER BY o.created_at DESC")
    todos_orcamentos = cursor.fetchall()

    cursor.close()
    # Mude o retorno aqui:
    return render_template("orcamento_eventos.html", clientes=clientes, produtos=produtos, kits=kits, todos_orcamentos=todos_orcamentos, now=datetime.now())




# ----------------------------------------------------------------------
# ROTA: DELETAR EVENTO E ORÇAMENTO ASSOCIADO
# ----------------------------------------------------------------------

@app.route("/deletar_evento/<int:evento_id>", methods=["POST"])
def deletar_evento(evento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("controle_eventos"))
    
    cursor = db.cursor(dictionary=True)
    try:
        # 1. Buscar detalhes do evento antes de deletar, incluindo o orcamento_id
        cursor.execute("""
            SELECT nome_evento, valor_total, valor_pago, orcamento_id 
            FROM eventos 
            WHERE id = %s
        """, (evento_id,))
        evento_a_deletar = cursor.fetchone()
        
        if not evento_a_deletar:
            flash("Evento não encontrado para exclusão.", "error")
            return redirect(url_for("controle_eventos"))

        nome_evento = evento_a_deletar['nome_evento']
        valor_pago = evento_a_deletar.get('valor_pago', 0) or 0
        valor_total = evento_a_deletar.get('valor_total', 0) or 0
        orcamento_id = evento_a_deletar.get('orcamento_id')

        # 2. 🔻 Excluir todos os lançamentos de fluxo de caixa relacionados a este evento
        # Usa correspondência parcial no campo 'descricao' e 'observacoes'
        # Assim, remove todos os pagamentos parciais e totais, sem afetar outros eventos
        descricao_like = f"%Receita do evento: {nome_evento}%"
        observacao_like = f"%Pagamento%{evento_id}%"
        cursor.execute("""
            DELETE FROM fluxo_caixa 
            WHERE (descricao LIKE %s OR observacoes LIKE %s)
            AND tipo = 'Receita'
        """, (descricao_like, observacao_like))

        # 3. Excluir os itens do evento (produtos e kits) e devolver ao estoque
        cursor.execute("""
            SELECT material_id, kit_id, quantidade 
            FROM montagem_materiais 
            WHERE evento_id = %s
        """, (evento_id,))
        itens_do_evento = cursor.fetchall()

        for item in itens_do_evento:
            if item['material_id']:
                # Devolver produtos ao estoque
                cursor.execute("""
                    UPDATE estoque 
                    SET quantidade_estoque = quantidade_estoque + %s 
                    WHERE id = %s
                """, (item['quantidade'], item['material_id']))
            elif item['kit_id']:
                # Liberar kits associados ao evento
                cursor.execute("""
                    UPDATE kits 
                    SET status = 'disponivel' 
                    WHERE id = %s
                """, (item['kit_id'],))

        # 4. Excluir os registros de montagem de materiais
        cursor.execute("DELETE FROM montagem_materiais WHERE evento_id = %s", (evento_id,))

        # 5. Excluir orçamento associado (se existir)
        if orcamento_id:
            cursor.execute("DELETE FROM orcamentos WHERE id = %s", (orcamento_id,))
            print(f"DEBUG: Orçamento ID {orcamento_id} excluído.")

        # 6. Excluir o evento da tabela principal
        cursor.execute("DELETE FROM eventos WHERE id = %s", (evento_id,))

        # 7. Registrar log da exclusão completa
        descricao_log = (
            f"Evento '{nome_evento}' (ID {evento_id}) excluído com sucesso. "
            f"Orçamento associado: {orcamento_id if orcamento_id else 'N/A'}. "
            f"Pagamentos parciais e totais removidos do fluxo de caixa."
        )
        registrar_log_atividade(db, 'EXCLUSAO', evento_id, descricao_log)

        # Commit final
        db.commit()

        flash('Evento excluído com sucesso! Itens retornaram ao estoque, '
              'pagamentos removidos do fluxo de caixa e orçamento associado excluído.', 'success')

    except Exception as e:
        db.rollback()
        flash(f'Ocorreu um erro ao excluir o evento: {e}', 'error')
        print(f"ERRO DELETAR EVENTO: {e}")

    finally:
        cursor.close()

    return redirect(url_for("controle_eventos"))




@app.route("/registrar_pagamento/<int:evento_id>", methods=["POST"])
def registrar_pagamento(evento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("controle_eventos"))
    
    pagamento_status = request.form.get("pagamento_status")
    valor_pago_form = request.form.get("valor_pago")  # valor informado no formulário
    meio_pagamento = request.form.get("meio_pagamento")

    cursor = db.cursor(dictionary=True)
    
    try:
        # Buscar o evento para validar o valor total e o que já foi pago
        cursor.execute("SELECT nome_evento, valor_total, valor_pago FROM eventos WHERE id = %s", (evento_id,))
        evento = cursor.fetchone()

        if not evento:
            flash("Evento não encontrado.", 'error')
            return redirect(url_for("controle_eventos"))

        valor_total_evento = Decimal(evento["valor_total"] or 0)
        valor_pago_atual = Decimal(evento["valor_pago"] or 0)
        valor_pago_form = Decimal(valor_pago_form or 0)

        # Saldo pendente antes do novo pagamento
        saldo_pendente = valor_total_evento - valor_pago_atual

        # 🔹 Validação do pagamento parcial
        if pagamento_status == "Parcial":
            if valor_pago_form <= 0:
                flash("Informe um valor válido para pagamento parcial.", 'error')
                return redirect(url_for("controle_eventos"))
            if valor_pago_form > saldo_pendente:
                flash("O valor parcial não pode ser maior que o saldo pendente.", 'error')
                return redirect(url_for("controle_eventos"))

            valor_a_registrar = valor_pago_form

        # 🔹 Pagamento total (somente o que falta é registrado)
        elif pagamento_status == "Total":
            valor_a_registrar = saldo_pendente

        else:
            flash("Status de pagamento inválido.", 'error')
            return redirect(url_for("controle_eventos"))

        # Atualiza o total pago no evento
        novo_valor_pago = valor_pago_atual + valor_a_registrar
        cursor.execute("""
            UPDATE eventos 
            SET status_pagamento = %s, valor_pago = %s 
            WHERE id = %s
        """, (pagamento_status, novo_valor_pago, evento_id))

        # 🔹 Registra apenas a diferença no fluxo de caixa
        if valor_a_registrar > 0:
            cursor.execute("""
                INSERT INTO fluxo_caixa (data, descricao, tipo, valor, observacoes) 
                VALUES (%s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                f"Receita do evento: {evento['nome_evento']}",
                "Receita",
                valor_a_registrar,
                f"Pagamento {pagamento_status} do evento (ID {evento_id})."
            ))

        db.commit()
        flash(f"Pagamento {pagamento_status} registrado com sucesso!", 'success')

    except Exception as e:
        db.rollback()
        flash(f"Ocorreu um erro ao registrar o pagamento: {e}", 'error')

    finally:
        cursor.close()
    
    return redirect(url_for("controle_eventos"))




# No seu arquivo app.py


@app.route("/relatorio_eventos")
def relatorio_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("index"))

    cursor = db.cursor(dictionary=True)

    # 1. Obter parâmetros de filtro da URL
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    tipo_filtro = request.args.get('tipo_filtro', 'todos')  # 'todos' é o valor padrão
    tipo_pagamento_filtro = request.args.get('tipo_pagamento', 'todos')  # Filtro de pagamento (Total, Parcial, Pendente)

    # 2. Construir a consulta SQL dinâmica
    where_clauses = []
    params = []

    if data_inicio:
        where_clauses.append("e.data_evento >= %s")
        params.append(data_inicio)
    if data_fim:
        where_clauses.append("e.data_evento <= %s")
        params.append(data_fim)
    if tipo_filtro and tipo_filtro != 'todos':
        where_clauses.append("e.tipo_evento = %s")
        params.append(tipo_filtro)
    if tipo_pagamento_filtro and tipo_pagamento_filtro != 'todos':
        where_clauses.append("e.status_pagamento = %s")  # Buscar diretamente da tabela 'eventos'
        params.append(tipo_pagamento_filtro)

    # Junta as cláusulas com 'AND' ou usa '1=1' se não houver filtros
    query_filter = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 3. Buscar a lista de eventos filtrados
    query_eventos = f"""
        SELECT 
            e.id, e.nome_evento, e.data_evento, e.tipo_evento,
            e.status, e.valor_total, c.nome as cliente_nome,
            e.status_pagamento
        FROM eventos e 
        JOIN clientes c ON e.cliente_id = c.id
        WHERE {query_filter}
        ORDER BY e.data_evento DESC
    """
    cursor.execute(query_eventos, tuple(params))
    eventos_filtrados = cursor.fetchall()

    # 4. Calcular estatísticas com base nos filtros
    stats = {}
    query_stats_base = f"FROM eventos e WHERE {query_filter}"

    cursor.execute(f"SELECT COUNT(*) as total {query_stats_base}", tuple(params))
    stats['total_filtrado'] = cursor.fetchone()['total'] or 0

    cursor.execute(f"SELECT SUM(valor_total) as total_valor {query_stats_base}", tuple(params))
    stats['valor_total_filtrado'] = cursor.fetchone()['total_valor'] or 0

    cursor.execute(f"SELECT status, COUNT(*) as count {query_stats_base} GROUP BY status", tuple(params))
    stats['eventos_por_status'] = cursor.fetchall()

    cursor.execute(f"SELECT status_pagamento, COUNT(*) as count {query_stats_base} GROUP BY status_pagamento", tuple(params))
    stats['pagamentos_por_status'] = cursor.fetchall()  # Adiciona os pagamentos por status

    # 5. Obter todos os tipos de evento para o dropdown do filtro
    cursor.execute("SELECT DISTINCT tipo_evento FROM eventos WHERE tipo_evento IS NOT NULL ORDER BY tipo_evento")
    tipos_de_evento = cursor.fetchall()

    cursor.close()

    return render_template(
        "relatorio_eventos.html",
        eventos_filtrados=eventos_filtrados,
        stats=stats,
        tipos_de_evento=tipos_de_evento,
        # Envia os valores dos filtros de volta para o template
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo_filtro=tipo_filtro,
        tipo_pagamento_filtro=tipo_pagamento_filtro  # Passa o filtro de pagamento para o template
    )


@app.route("/exportar_relatorio_eventos")
def exportar_relatorio_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro de conexão", "error")
        return redirect(url_for('relatorio_eventos'))

    # Pega os mesmos filtros da rota de relatório
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    tipo_filtro = request.args.get('tipo_filtro', 'todos')
    tipo_pagamento_filtro = request.args.get('tipo_pagamento', 'todos')  # Filtro de pagamento

    where_clauses = []
    params = []

    # Adiciona filtros para data
    if data_inicio:
        where_clauses.append("e.data_evento >= %s")
        params.append(data_inicio)
    if data_fim:
        where_clauses.append("e.data_evento <= %s")
        params.append(data_fim)

    # Adiciona filtro para tipo de evento
    if tipo_filtro and tipo_filtro != 'todos':
        where_clauses.append("e.tipo_evento = %s")
        params.append(tipo_filtro)

    # Adiciona filtro para tipo de pagamento
    if tipo_pagamento_filtro and tipo_pagamento_filtro != 'todos':
        where_clauses.append("p.status_pagamento = %s")
        params.append(tipo_pagamento_filtro)

    query_filter = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    query = f"""
        SELECT 
            e.data_evento as 'Data do Evento',
            e.nome_evento as 'Nome do Evento',
            c.nome as 'Cliente',
            e.tipo_evento as 'Tipo',
            e.status as 'Status',
            e.valor_total as 'Valor Total (R$)',
            p.status_pagamento as 'Status de Pagamento'
        FROM eventos e 
        JOIN clientes c ON e.cliente_id = c.id
        LEFT JOIN pagamentos p ON e.id = p.evento_id  # Assuming 'pagamentos' is the table that holds payment information
        WHERE {query_filter}
        ORDER BY e.data_evento DESC
    """

    # Executa a consulta
    df = pd.read_sql(query, db, params=tuple(params))

    # Se a consulta retornar dados, formate as colunas
    if not df.empty:
        df['Data do Evento'] = pd.to_datetime(df['Data do Evento']).dt.strftime('%d/%m/%Y %H:%M')

    # Cria o arquivo Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio de Eventos')

    # Prepara o arquivo para download
    output.seek(0)
    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=relatorio_de_eventos.xlsx"
    response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return response



@app.route("/fluxo_caixa", methods=["GET", "POST"])
def fluxo_caixa():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("index"))
        
    if request.method == "POST":
        # Lógica para adicionar nova transação (sem alterações)
        data = request.form.get("data")
        descricao = request.form.get("descricao")
        tipo = request.form.get("tipo")
        valor = request.form.get("valor")
        observacoes = request.form.get("observacoes")
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO fluxo_caixa (data, descricao, tipo, valor, observacoes) VALUES (%s, %s, %s, %s, %s)",
                           (data, descricao, tipo, valor, observacoes))
            db.commit()
            cursor.close()
            flash("Transação cadastrada com sucesso!", 'success')
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", 'error')
        return redirect(url_for('fluxo_caixa'))

    # --- NOVA LÓGICA DE FILTROS E RELATÓRIO (GET) ---
    cursor = db.cursor(dictionary=True)
    
    # Pega os parâmetros do filtro da URL
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    tipo_filtro = request.args.get('tipo_filtro', 'todos')

    # Monta a consulta SQL dinamicamente
    where_clauses = []
    params = []

    if data_inicio:
        where_clauses.append("data >= %s")
        params.append(data_inicio)
    if data_fim:
        where_clauses.append("data <= %s")
        params.append(data_fim)
    if tipo_filtro != 'todos':
        where_clauses.append("tipo = %s")
        params.append(tipo_filtro)

    query_filter = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Busca as transações filtradas
    cursor.execute(f"SELECT * FROM fluxo_caixa WHERE {query_filter} ORDER BY data DESC, id DESC", tuple(params))
    transacoes = cursor.fetchall()

    # Calcula os totais filtrados
    cursor.execute(f"SELECT SUM(valor) as total FROM fluxo_caixa WHERE tipo = 'Receita' AND {query_filter}", tuple(['Receita'] + params if 'tipo' in query_filter else params))
    receitas_filtradas = cursor.fetchone()['total'] or 0
    
    cursor.execute(f"SELECT SUM(valor) as total FROM fluxo_caixa WHERE tipo = 'Despesa' AND {query_filter}", tuple(['Despesa'] + params if 'tipo' in query_filter else params))
    despesas_filtradas = cursor.fetchone()['total'] or 0
    
    cursor.close()
    
    saldo_filtrado = receitas_filtradas - despesas_filtradas
    
    now = datetime.now()
    
    return render_template("fluxo_caixa.html", 
                           transacoes=transacoes, 
                           receitas=receitas_filtradas, 
                           despesas=despesas_filtradas, 
                           saldo=saldo_filtrado, 
                           now=now,
                           # Envia os filtros de volta para preencher os campos
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           tipo_filtro=tipo_filtro)

@app.route("/exportar_fluxo_caixa")
def exportar_fluxo_caixa_excel():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None: return "Erro de conexão", 500
    
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    tipo_filtro = request.args.get('tipo_filtro', 'todos')
    
    where_clauses = []
    params = []
    if data_inicio:
        where_clauses.append("data >= %s")
        params.append(data_inicio)
    if data_fim:
        where_clauses.append("data <= %s")
        params.append(data_fim)
    if tipo_filtro != 'todos':
        where_clauses.append("tipo = %s")
        params.append(tipo_filtro)
    
    query_filter = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    query = f"SELECT data, descricao, tipo, valor, observacoes FROM fluxo_caixa WHERE {query_filter} ORDER BY data DESC, id DESC"
    
    df = pd.read_sql(query, db, params=tuple(params))
    
    # Renomeia colunas para o Excel
    df.rename(columns={
        'data': 'Data',
        'descricao': 'Descrição',
        'tipo': 'Tipo',
        'valor': 'Valor (R$)',
        'observacoes': 'Observações'
    }, inplace=True)

    # Formata a coluna de data
    if not df.empty:
        df['Data'] = pd.to_datetime(df['Data']).dt.strftime('%d/%m/%Y')

    # Cria o arquivo Excel em memória
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Fluxo de Caixa')
    
    output.seek(0)
    
    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=relatorio_fluxo_caixa.xlsx"
    response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    return response
@app.route("/montagem_evento", methods=["GET", "POST"])
def montagem_evento():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        flash("Erro ao conectar ao banco de dados.", 'error')
        return redirect(url_for("montagem_evento"))
        
    if request.method == "POST":
        evento_id = request.form.get("evento_id")
        tipo_material = request.form.get("tipo_material")
        material_id = request.form.get("material_id")
        quantidade = request.form.get("quantidade")
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO montagem_materiais (evento_id, tipo_material, material_id, quantidade) VALUES (%s, %s, %s, %s)",
                           (evento_id, tipo_material, material_id, quantidade))
            db.commit()
            cursor.close()
            flash("Material adicionado à montagem do evento com sucesso!", 'success')
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", 'error')
            
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, nome FROM estoque WHERE tipo_material = 'descartavel'")
    materiais_descartaveis = cursor.fetchall()
    cursor.execute("SELECT id, nome FROM estoque WHERE tipo_material = 'aluguel'")
    materiais_aluguel = cursor.fetchall()
    cursor.execute("SELECT id, nome FROM estoque WHERE tipo_material = 'venda'")
    materiais_venda = cursor.fetchall()
    cursor.execute("SELECT id, nome_evento FROM eventos")
    eventos = cursor.fetchall()
    cursor.execute("""
        SELECT mm.id, mm.quantidade, e.nome_evento,
                CASE 
                    WHEN mm.tipo_material = 'descartavel' THEN (SELECT nome FROM estoque WHERE id = mm.material_id)
                    WHEN mm.tipo_material = 'aluguel' THEN (SELECT nome FROM estoque WHERE id = mm.material_id)
                    WHEN mm.tipo_material = 'venda' THEN (SELECT nome FROM estoque WHERE id = mm.material_id)
                END AS nome_material
        FROM montagem_materiais mm
        JOIN eventos e ON mm.evento_id = e.id
        ORDER BY e.data_evento DESC
    """)
    montagem_materiais = cursor.fetchall()
    cursor.close()

    return render_template("montagem_evento.html", 
                           eventos=eventos, 
                           materiais_descartaveis=materiais_descartaveis, 
                           materiais_aluguel=materiais_aluguel,
                           materiais_venda=materiais_venda,
                           montagem_materiais=montagem_materiais)



if __name__ == "__main__":
    with app.app_context():
        create_initial_admin_user()
    app.run(debug=True)
