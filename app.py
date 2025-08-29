# Importa as classes e funções necessárias do Flask e o conector MySQL
import os
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from mysql.connector import Error

# Cria a instância da aplicação Flask.
app = Flask(__name__)
# A secret_key é necessária para sessões e mensagens flash
app.secret_key = os.urandom(24)

# Configurações do banco de dados MySQL.
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'db_evento',
    'port': 3306  # Porta padrão do MySQL
}

def get_db():
    """Conecta ao banco de dados MySQL e retorna a conexão."""
    db = getattr(g, '_database', None)
    if db is None:
        try:
            db = g._database = mysql.connector.connect(**MYSQL_CONFIG)
        except Error as e:
            print(f"Erro ao conectar ao MySQL: {e}")
            flash("Erro ao conectar ao banco de dados.", 'error')
            return None
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Fecha a conexão com o banco de dados no final da requisição."""
    db = getattr(g, '_database', None)
    if db is not None and db.is_connected():
        db.close()

# Rota para a página inicial (painel de controle).
@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html", username=session["username"], role=session.get("role"))

# Rota para o formulário de login.
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        db = get_db()
        if db is None:
            return redirect(url_for("login"))
        
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and user['password'] == password:
            session["logged_in"] = True
            session["username"] = username
            session["role"] = user['role']
            return redirect(url_for("index"))
        else:
            error = "Nome de usuário ou senha inválidos. Tente novamente."

    return render_template("login.html", error=error)

# Rota para o logout.
@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("username", None)
    session.pop("role", None)
    return redirect(url_for("login"))

# Rota para o cadastro de usuário (restrita a usuários com a role 'admin')
@app.route("/cadastro_usuario", methods=["GET", "POST"])
def cadastro_usuario():
    if not session.get("logged_in") or session.get("role") != "admin":
        return redirect(url_for("index"))
    
    db = get_db()
    if db is None:
        return redirect(url_for("cadastro_usuario"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                           (username, password, role))
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

# Rota para a tela de Estoque
@app.route("/estoque_evento", methods=["GET", "POST"])
def estoque_evento():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        return redirect(url_for("estoque_evento"))

    if request.method == 'POST':
        nome = request.form.get("nome_material").strip().lower()
        tipo_material = request.form.get("tipo_material")
        unidade_medida = request.form.get("unidade_medida") or "unidade"
        quantidade_estoque = request.form.get("quantidade_estoque")
        preco_compra = request.form.get("preco_compra")
        preco_repasse = request.form.get("preco_repasse")
        
        # Campo opcional para descartável
        quantidade_venda = request.form.get("quantidade_venda") if tipo_material == 'descartavel' else 0

        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM estoque WHERE nome = %s", (nome,))
        if cursor.fetchone()[0] > 0:
            flash('Material com este nome já existe. Por favor, escolha outro.', 'error')
            cursor.close()
            return redirect(url_for('estoque_evento'))

        # Converte para tipos corretos
        try:
            quantidade_estoque = float(quantidade_estoque) if quantidade_estoque else 0.0
            preco_compra = float(preco_compra) if preco_compra else 0.0
            preco_repasse = float(preco_repasse) if preco_repasse else 0.0
            quantidade_venda = float(quantidade_venda) if quantidade_venda else 0.0
        except (ValueError, TypeError):
            flash("Erro ao converter dados numéricos. Verifique os valores inseridos.", 'error')
            cursor.close()
            return redirect(url_for('estoque_evento'))

        try:
            cursor.execute(
                """
                INSERT INTO estoque (nome, tipo_material, unidade_medida, quantidade_venda, quantidade_estoque, preco_compra, preco_repasse) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (nome, tipo_material, unidade_medida, quantidade_venda, quantidade_estoque, preco_compra, preco_repasse)
            )
            db.commit()
            flash("Material cadastrado com sucesso!", 'success')
        except Exception as e:
            db.rollback()
            flash(f"Ocorreu um erro ao salvar o material: {e}", 'error')
        finally:
            cursor.close()

        return redirect(url_for('estoque_evento'))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM estoque")
    materiais = cursor.fetchall()
    cursor.close()
    return render_template('estoque_evento.html', materiais=materiais)

# Rota para a consulta de estoque
@app.route("/consulta_estoque")
def consulta_estoque():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        return redirect(url_for("consulta_estoque"))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, nome, tipo_material, unidade_medida, quantidade_estoque, preco_compra, preco_repasse FROM estoque")
    materiais = cursor.fetchall()
    cursor.close()
    
    return render_template("consulta_estoque.html", materiais=materiais)

@app.route("/deletar_material/<int:material_id>", methods=["POST"])
def deletar_material(material_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        return redirect(url_for("consulta_estoque"))
        
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM estoque WHERE id = %s", (material_id,))
        db.commit()
        cursor.close()
        flash('Material excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Ocorreu um erro ao excluir o material: {e}', 'error')
    
    return redirect(url_for('consulta_estoque'))
    
# Rota para o cadastro de clientes
@app.route("/cadastro_cliente", methods=["GET", "POST"])
def cadastro_cliente():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        return redirect(url_for("cadastro_cliente"))
    
    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        endereco = request.form.get("endereco")
        
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO clientes (nome, telefone, email, endereco) VALUES (%s, %s, %s, %s)",
                           (nome, telefone, email, endereco))
            db.commit()
            cursor.close()
            flash("Cliente cadastrado com sucesso!", 'success')
        except mysql.connector.IntegrityError:
            flash("E-mail já existe. Por favor, insira um e-mail diferente.", 'error')
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", 'error')
            
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()
    cursor.close()
    
    return render_template("cadastro_cliente.html", clientes=clientes)
    
# Rota para a tabela de preços
@app.route("/tabela_precos", methods=["GET", "POST"])
def tabela_precos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
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

# Rota para o cadastro de eventos
@app.route("/eventos", methods=["GET", "POST"])
def eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        return redirect(url_for("eventos"))
    
    if request.method == "POST":
        nome_evento = request.form.get("nome_evento")
        cliente_id = request.form.get("cliente_id")
        data_evento = request.form.get("data_evento")
        recolhimento_evento = request.form.get("recolhimento_evento")
        observacoes = request.form.get("observacoes")
        
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO eventos (nome_evento, cliente_id, data_evento, recolhimento_evento, observacoes) VALUES (%s, %s, %s, %s, %s)",
                           (nome_evento, cliente_id, data_evento, recolhimento_evento, observacoes))
            db.commit()
            cursor.close()
            flash("Evento cadastrado com sucesso!", 'success')
        except Exception as e:
            flash(f"Ocorreu um erro: {e}", 'error')
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, nome FROM clientes")
    clientes = cursor.fetchall()
    cursor.execute("SELECT e.id, e.nome_evento, e.data_evento, e.recolhimento_evento, e.observacoes, c.nome as cliente_nome FROM eventos e JOIN clientes c ON e.cliente_id = c.id ORDER BY e.data_evento")
    eventos = cursor.fetchall()
    cursor.close()
    
    return render_template("eventos.html", clientes=clientes, eventos=eventos)

# Rota para o calendário de eventos
@app.route("/calendario_eventos")
def calendario_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        return redirect(url_for("calendario_eventos"))
        
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT e.nome_evento, e.data_evento, c.nome as cliente_nome FROM eventos e JOIN clientes c ON e.cliente_id = c.id ORDER BY e.data_evento")
    eventos = cursor.fetchall()
    cursor.close()
    
    return render_template("calendario_eventos.html", eventos=eventos)

# Rota para o controle de eventos
@app.route("/controle_eventos")
def controle_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        return redirect(url_for("controle_eventos"))
        
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT e.id, e.nome_evento, e.data_evento, e.recolhimento_evento, e.observacoes, c.nome as cliente_nome, e.status FROM eventos e JOIN clientes c ON e.cliente_id = c.id ORDER BY e.data_evento")
    eventos = cursor.fetchall()
    cursor.close()

    return render_template("controle_eventos.html", eventos=eventos)
    
# Rota para deletar um evento
@app.route("/deletar_evento/<int:evento_id>", methods=["POST"])
def deletar_evento(evento_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        return redirect(url_for("controle_eventos"))
        
    try:
        cursor = db.cursor()
        # Primeiro, delete todos os materiais de montagem associados a este evento
        cursor.execute("DELETE FROM montagem_materiais WHERE evento_id = %s", (evento_id,))
        
        # Em seguida, delete o evento
        cursor.execute("DELETE FROM eventos WHERE id = %s", (evento_id,))
        db.commit()
        cursor.close()
        flash('Evento excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Ocorreu um erro ao excluir o evento: {e}', 'error')
        print(f"Erro ao deletar o evento: {e}")
        
    return redirect(url_for("controle_eventos"))

# Rota para o relatório de eventos
@app.route("/relatorio_eventos")
def relatorio_eventos():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    db = get_db()
    if db is None:
        return redirect(url_for("relatorio_eventos"))
        
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as total FROM eventos")
    total_eventos = cursor.fetchone()['total']
    cursor.execute("SELECT status, COUNT(*) as count FROM eventos GROUP BY status")
    eventos_por_status = cursor.fetchall()
    cursor.close()
    
    return render_template("relatorio_eventos.html", total_eventos=total_eventos, eventos_por_status=eventos_por_status)

# Rota para o fluxo de caixa
@app.route("/fluxo_caixa", methods=["GET", "POST"])
def fluxo_caixa():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
        return redirect(url_for("fluxo_caixa"))
        
    if request.method == "POST":
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

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM fluxo_caixa ORDER BY data DESC")
    transacoes = cursor.fetchall()

    cursor.execute("SELECT SUM(valor) as total FROM fluxo_caixa WHERE tipo = 'Receita'")
    receitas = cursor.fetchone()['total'] or 0
    cursor.execute("SELECT SUM(valor) as total FROM fluxo_caixa WHERE tipo = 'Despesa'")
    despesas = cursor.fetchone()['total'] or 0
    cursor.close()
    
    saldo = receitas - despesas

    return render_template("fluxo_caixa.html", transacoes=transacoes, receitas=receitas, despesas=despesas, saldo=saldo)

# Rota para a montagem do evento
@app.route("/montagem_evento", methods=["GET", "POST"])
def montagem_evento():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    db = get_db()
    if db is None:
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
    
    cursor.execute("SELECT id, nome_evento FROM eventos")
    eventos = cursor.fetchall()
    
    cursor.execute("""
        SELECT mm.id, mm.quantidade, e.nome_evento,
                CASE 
                    WHEN mm.tipo_material = 'descartavel' THEN (SELECT nome FROM estoque WHERE id = mm.material_id)
                    WHEN mm.tipo_material = 'aluguel' THEN (SELECT nome FROM estoque WHERE id = mm.material_id)
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
                             montagem_materiais=montagem_materiais)

if __name__ == "__main__":
    app.run(debug=True)
