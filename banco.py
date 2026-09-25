import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
BANCO = str(BASE_DIR / "confeitaria.db")


def conectar():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao

def salvar_foto_perfil(cliente_id, arquivo):
    conexao = conectar()

    foto = arquivo.read()
    tipo = arquivo.content_type

    conexao.execute("""
        UPDATE clientes
        SET foto = ?, foto_tipo = ?
        WHERE id = ?
    """, (foto, tipo, cliente_id))

    conexao.commit()
    conexao.close()


def criar_banco():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS administradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL
        )
    """)

    senha_admin_hash = generate_password_hash("admin123")
    cursor.execute("""
        INSERT OR IGNORE INTO administradores
        (nome, email, senha)
        VALUES (?, ?, ?)
    """, (
        "Administrador",
        "admin@confeitaria.com",
        senha_admin_hash
    ))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            nickname TEXT,
            genero TEXT,
            telefone TEXT,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            rua TEXT,
            numero TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            foto BLOB,
            foto_tipo TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            sabor TEXT NOT NULL,
            preco REAL NOT NULL,
            foto TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            item TEXT NOT NULL,
            sabor TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            preco REAL NOT NULL,
            status TEXT NOT NULL,
            data TEXT NOT NULL,
            pagamento_info TEXT,
            endereco TEXT,
            taxa_entrega REAL DEFAULT 0,
            cor TEXT,
            confeito TEXT,
            papel_arroz TEXT,
            glace TEXT,
            pasta_americana TEXT,
            observacao TEXT,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)

    colunas = cursor.execute("""
        PRAGMA table_info(clientes)
    """).fetchall()

    nomes_colunas = [coluna["name"] for coluna in colunas]

    if "foto_tipo" not in nomes_colunas:
        cursor.execute("""
            ALTER TABLE clientes
            ADD COLUMN foto_tipo TEXT
        """)

    conexao.commit()
    conexao.close()


def inserir_produtos():
    conexao = conectar()
    cursor = conexao.cursor()

    quantidade = cursor.execute(
        "SELECT COUNT(*) FROM produtos"
    ).fetchone()[0]

    if quantidade == 0:
        produtos = {
            "bolo": {
                "chocolate": 80,
                "morango": 90,
                "baunilha": 75,
                "limao": 70,
                "amendoim": 65,
                "banana": 65
            },

            "cupcake": {
                "chocolate": 8,
                "morango": 10,
                "baunilha": 7,
                "limão": 7
            },

            "torta": {
                "limao": 60,
                "frutas-vermelhas": 80,
                "chocolate": 70,
                "frango": 60,
                "carne-seca": 75
            },

            "docinhos": {
                "brigadeiros": 3,
                "beijinho": 3,
                "leite-ninho": 4,
                "bicho-de-pé": 5,
                "churros": 5
            },

            "salgadinhos": {
                "coxinha": 4,
                "bolinha-de-queijo": 4,
                "croquete-carne": 4,
                "croquete-frios": 5
            }
        }

        for categoria, sabores in produtos.items():
            for sabor, preco in sabores.items():
                cursor.execute("""
                    INSERT INTO produtos
                    (categoria, sabor, preco)
                    VALUES (?, ?, ?)
                """, (
                    categoria,
                    sabor,
                    preco
                ))

    conexao.commit()
    conexao.close()

def sincronizar_fotos_produtos():
    """Relaciona as fotos existentes aos produtos pelo nome produto_<id>.*."""
    pasta = BASE_DIR / "static" / "uploads" / "produtos"
    conexao = conectar()
    produtos = conexao.execute("SELECT id, foto FROM produtos").fetchall()
    for produto in produtos:
        encontrado = None
        for ext in ("jpg", "jpeg", "png", "webp", "gif"):
            caminho = pasta / f"produto_{produto['id']}.{ext}"
            if caminho.exists():
                encontrado = caminho.name
                break
        if encontrado and produto["foto"] != encontrado:
            conexao.execute("UPDATE produtos SET foto = ? WHERE id = ?", (encontrado, produto["id"]))
    conexao.commit()
    conexao.close()
