import os
from dotenv import load_dotenv
import mysql.connector
from flask import g
from mysql.connector import Error, errorcode
import bcrypt

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

# Configurações do banco de dados MySQL.
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'root')
DB_NAME = os.getenv('DB_NAME', 'db_evento')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# Configurações para conexão SEM o nome do DB (necessário para criar o DB)
MYSQL_ROOT_CONFIG = {
    'host': DB_HOST,
    'user': DB_USER,
    'password': DB_PASSWORD,
    'port': DB_PORT
}

# Configurações para conexão COM o nome do DB
MYSQL_CONFIG = {
    'host': DB_HOST,
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME,
    'port': DB_PORT
}

# --------------------------------------------------------------------------------
# DDL (Data Definition Language) - Esquema de Criação das Tabelas
# --------------------------------------------------------------------------------
# A ordem é importante para respeitar as chaves estrangeiras.
TABLES = {}

# 1. Tabela: users
TABLES['users'] = """
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL, -- Armazena o hash bcrypt
    role ENUM('admin', 'user') DEFAULT 'user' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 2. Tabela: clientes
TABLES['clientes'] = """
CREATE TABLE clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    telefone VARCHAR(20),
    email VARCHAR(255) NOT NULL UNIQUE, -- Garante que cada cliente tenha um e-mail único
    cpf VARCHAR(11) NOT NULL UNIQUE,
    cep VARCHAR(8),
    endereco VARCHAR(255),
    bairro VARCHAR(100),
    cidade VARCHAR(100),
    uf VARCHAR(2),
    numero VARCHAR(20),
    complemento VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 3. Tabela: configuracoes_email
TABLES['configuracoes_email'] = """
CREATE TABLE configuracoes_email (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    codigo_app VARCHAR(255) NOT NULL, -- Código/Senha de App do Gmail
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 4. Tabela: estoque
TABLES['estoque'] = """
CREATE TABLE estoque (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    tipo_material ENUM('descartavel', 'aluguel', 'venda', 'kit_componente') NOT NULL,
    unidade_medida VARCHAR(50) DEFAULT 'unidade',
    quantidade_venda DECIMAL(10, 2), -- Quantidade em uma unidade de medida maior (ex: unidades em uma caixa)
    quantidade_estoque DECIMAL(10, 2) NOT NULL,
    preco_compra DECIMAL(10, 2) NOT NULL,
    preco_repasse DECIMAL(10, 2) NOT NULL, -- Preço de venda/aluguel para o cliente
    foto_path VARCHAR(255),
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 5. Tabela: kits
TABLES['kits'] = """
CREATE TABLE kits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    valor DECIMAL(10, 2) NOT NULL, -- Preço de repasse do kit
    foto_path VARCHAR(255),
    status ENUM('disponivel', 'em_uso', 'manutencao') DEFAULT 'disponivel' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 6. Tabela: kit_itens
TABLES['kit_itens'] = """
CREATE TABLE kit_itens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kit_id INT NOT NULL,
    material_id INT NOT NULL, -- Componente do kit (referência à tabela 'estoque')
    quantidade DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (kit_id) REFERENCES kits(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES estoque(id) ON DELETE RESTRICT, -- RESTRICT para evitar a exclusão de um produto que está em um kit
    UNIQUE KEY uk_kit_material (kit_id, material_id) -- Garante que um kit não tenha o mesmo material duas vezes
) ENGINE=InnoDB;
"""

# 7. Tabela: orcamentos
TABLES['orcamentos'] = """
CREATE TABLE orcamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    nome_evento VARCHAR(255) NOT NULL,
    tipo_evento VARCHAR(100),
    data_evento DATETIME NOT NULL,
    recolhimento_evento DATETIME,
    observacoes TEXT,
    valor_total DECIMAL(10, 2) NOT NULL,
    mao_de_obra DECIMAL(10, 2) DEFAULT 0.00,
    frete DECIMAL(10, 2) DEFAULT 0.00,
    itens_json JSON NOT NULL, -- Armazena os itens selecionados como JSON
    token VARCHAR(36) NOT NULL UNIQUE, -- Token de aprovação por e-mail
    status ENUM('Pendente', 'Aprovado', 'Recusado') DEFAULT 'Pendente' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
"""

# 8. Tabela: eventos
TABLES['eventos'] = """
CREATE TABLE eventos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    orcamento_id INT UNIQUE, -- Link para o orçamento que gerou este evento (OPCIONAL, pode ser NULL)
    cliente_id INT NOT NULL,
    nome_evento VARCHAR(255) NOT NULL,
    tipo_evento VARCHAR(100),
    data_evento DATETIME NOT NULL,
    recolhimento_evento DATETIME,
    observacoes TEXT,
    valor_total DECIMAL(10, 2) NOT NULL,
    valor_pago DECIMAL(10, 2) DEFAULT 0.00, -- Novo campo para rastrear o total pago
    mao_de_obra DECIMAL(10, 2) DEFAULT 0.00,
    frete DECIMAL(10, 2) DEFAULT 0.00,
    status ENUM('Pendente', 'Confirmado', 'Em Montagem', 'Finalizado', 'Finalização Parcial') DEFAULT 'Confirmado' NOT NULL,
    status_pagamento ENUM('Pendente', 'Parcial', 'Total') DEFAULT 'Pendente' NOT NULL,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
    FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id) ON DELETE SET NULL -- Se o orçamento for deletado, a chave externa é zerada
) ENGINE=InnoDB;
"""

# 9. Tabela: montagem_materiais
TABLES['montagem_materiais'] = """
CREATE TABLE montagem_materiais (
    id INT AUTO_INCREMENT PRIMARY KEY,
    evento_id INT NOT NULL,
    material_id INT, -- ID do produto da tabela 'estoque' (para produtos avulsos)
    kit_id INT, -- ID do kit da tabela 'kits' (para kits)
    quantidade DECIMAL(10, 2) NOT NULL,
    valor_item DECIMAL(10, 2), -- Valor do item no momento do cadastro do evento (para histórico)
    FOREIGN KEY (evento_id) REFERENCES eventos(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES estoque(id) ON DELETE RESTRICT,
    FOREIGN KEY (kit_id) REFERENCES kits(id) ON DELETE RESTRICT,
    -- Uma restrição para garantir que haja apenas material_id OU kit_id, mas não ambos.
    CONSTRAINT chk_material_or_kit CHECK (
        (material_id IS NULL AND kit_id IS NOT NULL) OR 
        (material_id IS NOT NULL AND kit_id IS NULL)
    )
) ENGINE=InnoDB;
"""

# 10. Tabela: fluxo_caixa
TABLES['fluxo_caixa'] = """
CREATE TABLE fluxo_caixa (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data DATE NOT NULL,
    descricao VARCHAR(255) NOT NULL,
    tipo ENUM('Receita', 'Despesa') NOT NULL,
    valor DECIMAL(10, 2) NOT NULL,
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 11. Tabela: log_atividades
TABLES['log_atividades'] = """
CREATE TABLE log_atividades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(50) NOT NULL, -- Ex: MUDANCA_STATUS_EVENTO, EXCLUSAO, CADASTRO_PRODUTO
    id_referencia INT, -- ID do registro (evento, produto, etc.) que foi alterado (pode ser NULL)
    descricao TEXT NOT NULL,
    data_log TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

# 12. Tabela: precos
TABLES['precos'] = """
CREATE TABLE precos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    tipo ENUM('servico', 'mao_de_obra', 'frete', 'outro') NOT NULL,
    preco DECIMAL(10, 2) NOT NULL
) ENGINE=InnoDB;
"""


# --------------------------------------------------------------------------------
# FUNÇÕES DE INICIALIZAÇÃO DO BANCO DE DADOS
# --------------------------------------------------------------------------------

def setup_database():
    """
    Tenta conectar ao servidor MySQL (sem DB), cria o banco de dados se não existir
    e garante que todas as tabelas estejam criadas.
    Esta função é chamada uma vez na inicialização do módulo.
    """
    print(f"--- Iniciando configuração do DB: {DB_NAME} ---")
    
    # 1. Tenta conectar ao servidor (sem especificar o DB)
    try:
        cnx = mysql.connector.connect(**MYSQL_ROOT_CONFIG)
        cursor = cnx.cursor()
    except Error as err:
        print(f"Erro CRÍTICO: Não foi possível conectar ao servidor MySQL. Verifique as credenciais no .env. Erro: {err}")
        return False

    # 2. Cria o banco de dados se não existir
    try:
        # Usa utf8mb4 e utf8mb4_unicode_ci para garantir suporte a emojis e caracteres complexos
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"Banco de dados '{DB_NAME}' garantido.")
        cnx.database = DB_NAME # Altera a conexão para usar o DB recém-criado/existente
    except Error as err:
        print(f"Falha ao criar/acessar o DB: {err}")
        cursor.close()
        cnx.close()
        return False
    
    # 3. Cria todas as tabelas, pulando se já existirem
    for name, ddl in TABLES.items():
        try:
            # Tenta criar a tabela. O InnoDB é usado por padrão na DDL.
            cursor.execute(ddl)
            print(f"Tabela {name}: OK (Criada).")
        except Error as err:
            if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                print(f"Tabela {name}: OK (Já existe).")
                continue # Continua para a próxima tabela
            else:
                # Erros como sintaxe ou Foreign Key podem aparecer aqui
                print(f"Tabela {name}: Erro CRÍTICO ao criar a tabela: {err}")
                
    cursor.close()
    cnx.close()
    print("--- Configuração do DB concluída com sucesso. ---")
    return True


# --------------------------------------------------------------------------------
# FUNÇÕES DO CONTEXTO DO FLASK
# --------------------------------------------------------------------------------

def get_db():
    """
    Conecta ao banco de dados MySQL e retorna a conexão.
    Armazena a conexão em `g` para que possa ser reutilizada na mesma requisição.
    """
    db = getattr(g, '_database', None)
    if db is None:
        try:
            # Garante a conexão ao DB com o nome especificado
            db = g._database = mysql.connector.connect(**MYSQL_CONFIG)
        except Error as e:
            # Se a conexão falhar, retorna None e o erro é logado no console principal (se houver)
            return None
    return db

def close_connection(exception):
    """Fecha a conexão com o banco de dados se ela existir."""
    db = getattr(g, '_database', None)
    if db is not None and db.is_connected():
        db.close()

def create_initial_admin_user():
    """Cria um usuário 'admin' inicial ou atualiza a senha se ele já existir."""
    db = get_db()
    if db is None:
        print("Erro ao conectar ao banco de dados para criar o usuário inicial.")
        return
    
    # Assuma a senha 'admin' se a variável de ambiente não estiver definida
    admin_password_env = os.getenv('ADMIN_PASSWORD', 'admin')

    cursor = None # Inicializa o cursor como None
    try:
        cursor = db.cursor(dictionary=True)
        # A tabela 'users' precisa existir para esta consulta rodar
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        user = cursor.fetchone()

        # O hash da senha
        hashed_password = bcrypt.hashpw(admin_password_env.encode('utf-8'), bcrypt.gensalt())
        hashed_password_str = hashed_password.decode('utf-8')

        if not user:
            # Cria um novo usuário 'admin'
            sql = "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)"
            cursor.execute(sql, ('admin', hashed_password_str, 'admin'))
            db.commit()
            print("Usuário 'admin' criado com sucesso! Senha padrão: (ADMIN_PASSWORD do .env)")
        
    except Error as e:
        print(f"Erro SQL ao criar/atualizar o usuário 'admin': {e}")
    except Exception as e:
        print(f"Erro geral ao criar/atualizar o usuário 'admin': {e}")
    finally:
        # CORREÇÃO: Fecha o cursor se ele foi criado, resolvendo o 'AttributeError'
        if cursor:
            cursor.close()


# --------------------------------------------------------------------------------
# LÓGICA DE INICIALIZAÇÃO NA PRIMEIRA IMPORTAÇÃO
# --------------------------------------------------------------------------------

# Chama a função de configuração do DB logo após a definição das funções
setup_database()