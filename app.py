import os
import random
import string
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for, session, flash, Response, send_file, abort)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from banco import conectar, criar_banco, inserir_produtos, salvar_foto_perfil, sincronizar_fotos_produtos, BANCO


app = Flask(__name__)
app.secret_key = 'chave_secreta_confeitaria'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PASTA_PRODUTOS = os.path.join(UPLOAD_FOLDER, 'produtos')
os.makedirs(PASTA_PRODUTOS, exist_ok=True)


def arquivo_permitido(nome):
    return (
        '.' in nome
        and nome.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)

@app.route('/produto/<int:produto_id>/imagem')
def imagem_produto(produto_id):
    """Entrega a imagem do produto diretamente a partir da pasta do projeto."""
    conexao = conectar()
    produto = conexao.execute(
        "SELECT foto FROM produtos WHERE id = ?", (produto_id,)
    ).fetchone()
    conexao.close()

    if not produto or not produto['foto']:
        abort(404)

    nome = os.path.basename(produto['foto'])
    caminho = os.path.join(PASTA_PRODUTOS, nome)

    if not os.path.isfile(caminho):
        abort(404)

    return send_file(caminho)


def atualizar_sessao_cliente(cliente):
    dados = dict(cliente)
    dados.pop('foto', None)
    dados.pop('foto_tipo', None)
    session['usuario'] = dados

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def web_login():

    email = request.form.get('email')
    senha = request.form.get('senha')
    opcao = request.form.get('tipo_usuario')

    conexao = conectar()
    cursor = conexao.cursor()

    if opcao == "1":
        cliente = cursor.execute("""
            SELECT *
            FROM clientes
            WHERE email = ?
        """, (email,)).fetchone()

        if cliente and check_password_hash(cliente['senha'], senha):
            conexao.close()
            atualizar_sessao_cliente(cliente)
            session['tipo_usuario'] = 'cliente'
            flash(f"Bem-vindo(a), {cliente['nome']}!", "success")
            return redirect(url_for('comprar_web'))

    elif opcao == "2":
        funcionario = cursor.execute("""
            SELECT *
            FROM funcionarios
            WHERE email = ?
        """, (email,)).fetchone()

        if funcionario and check_password_hash(funcionario['senha'], senha):
            conexao.close()
            session['usuario'] = dict(funcionario)
            session['tipo_usuario'] = 'funcionario'
            flash(f"Bem-vindo(a), {funcionario['nome']}!", "success")
            return redirect(url_for('ver_pedidos'))

    elif opcao == "3":
        administrador = cursor.execute("""
            SELECT *
            FROM administradores
            WHERE email = ?
        """, (email,)).fetchone()

        if administrador and check_password_hash(administrador['senha'], senha):
            conexao.close()
            session['usuario'] = dict(administrador)
            session['tipo_usuario'] = 'admin'
            flash(f"Bem-vindo(a), {administrador['nome']}!", "success")
            return redirect(url_for('admin_produtos'))

    conexao.close()
    flash("Login inválido!", "error")
    return redirect(url_for('index'))


@app.route('/cadastrar', methods=['POST'])
def web_cadastrar():
    opcao = request.form.get('tipo_usuario')
    nome = request.form.get('nome')
    email = request.form.get('email')
    senha = request.form.get('senha')

    # Criptografa a senha antes de salvar no banco
    senha_hash = generate_password_hash(senha)

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        if opcao == "1":
            cursor.execute("""
                INSERT INTO clientes
                (nome, nickname, genero, telefone, email, senha, rua, numero, bairro, cidade, estado, foto)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nome,
                nome,
                '',
                request.form.get('telefone'),
                email,
                senha_hash,
                request.form.get('rua'),
                request.form.get('numero'),
                request.form.get('bairro'),
                request.form.get('cidade'),
                request.form.get('estado'),
                ''))

        elif opcao == "2":
            cursor.execute("""
                INSERT INTO funcionarios
                (nome, email, senha)
                VALUES (?, ?, ?)
            """, (nome, email, senha_hash))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        if 'UNIQUE constraint failed' in str(erro):
            flash("Este email já está cadastrado!", "error")
        else:
            flash("Erro ao realizar cadastro.", "error")

        conexao.close()
        return redirect(url_for('index'))

    conexao.close()
    flash("Cadastro realizado com sucesso!", "success")
    return redirect(url_for('index'))

@app.route('/perfil/foto/<int:cliente_id>')
def foto_perfil(cliente_id):

    conexao = conectar()

    cliente = conexao.execute("""
        SELECT foto, foto_tipo
        FROM clientes
        WHERE id = ?
    """, (cliente_id,)).fetchone()

    conexao.close()

    if not cliente or not cliente['foto']:
        return '', 404

    return Response(
        cliente['foto'],
        mimetype=cliente['foto_tipo'] or 'image/jpeg'
    )

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():

    if 'usuario' not in session:
        return redirect(url_for('index'))

    if session.get('tipo_usuario') != 'cliente':
        flash("Somente clientes possuem perfil editável.", "error")
        return redirect(url_for('ver_pedidos'))

    cliente_id = session['usuario']['id']
    conexao = conectar()
    cursor = conexao.cursor()

    cliente = cursor.execute("""
        SELECT *
        FROM clientes
        WHERE id = ?
    """, (cliente_id,)).fetchone()

    if not cliente:
        conexao.close()
        session.clear()
        return redirect(url_for('index'))

    if request.method == 'POST':
        nickname = request.form.get('nickname')
        genero = request.form.get('genero')
        rua = request.form.get('rua')
        numero = request.form.get('numero')
        bairro = request.form.get('bairro')
        cidade = request.form.get('cidade')
        estado = request.form.get('estado')

        arquivo = request.files.get('foto')

        if arquivo and arquivo.filename:

            if not arquivo_permitido(arquivo.filename):
                conexao.close()
                flash(
                    "Formato de imagem inválido. Use PNG, JPG, JPEG, GIF ou WEBP.",
                    "error"
                )
                return redirect(url_for('perfil'))

            salvar_foto_perfil(cliente_id, arquivo)
        cursor.execute("""
            UPDATE clientes
            SET
                nickname = ?,
                genero = ?,
                rua = ?,
                numero = ?,
                bairro = ?,
                cidade = ?,
                estado = ?
            WHERE id = ?
        """, (nickname, genero, rua, numero, bairro, cidade, estado, cliente_id))

        conexao.commit()

        cliente_atualizado = cursor.execute("""
            SELECT *
            FROM clientes
            WHERE id = ?
        """, (cliente_id,)).fetchone()

        conexao.close()
        atualizar_sessao_cliente(cliente_atualizado)
        flash("Perfil atualizado com sucesso!", "success")
        return redirect(url_for('perfil'))
    conexao.close()

    return render_template('perfil.html', cliente=cliente)

@app.route('/admin/banco')
def admin_banco():
    """Visualizador acadêmico do SQLite, somente para administradores."""
    if 'usuario' not in session:
        return redirect(url_for('index'))
    if session.get('tipo_usuario') != 'admin':
        flash("Acesso permitido somente para administradores.", "error")
        return redirect(url_for('ver_pedidos'))

    import base64

    conexao = conectar()
    nomes = [
        row['name'] for row in conexao.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name <> 'sqlite_sequence'
            ORDER BY name
        """).fetchall()
    ]

    tabelas = []
    for nome in nomes:
        colunas = [dict(row) for row in conexao.execute(f'PRAGMA table_info("{nome}")').fetchall()]
        registros = []
        for row in conexao.execute(f'SELECT * FROM "{nome}"').fetchall():
            registro = dict(row)
            visual = {}
            for coluna, valor in registro.items():
                if coluna == 'foto' and isinstance(valor, bytes) and valor:
                    tipo = registro.get('foto_tipo') or 'image/jpeg'
                    visual[coluna] = {'tipo': 'imagem', 'src': f"data:{tipo};base64,{base64.b64encode(valor).decode('ascii')}"}
                elif coluna == 'foto' and nome == 'produtos' and isinstance(valor, str) and valor:
                    visual[coluna] = {'tipo': 'imagem_arquivo', 'src': url_for('static', filename=f'uploads/produtos/{valor}')}
                elif coluna == 'senha' and valor:
                    visual[coluna] = {'tipo': 'senha', 'valor': valor}
                elif isinstance(valor, bytes):
                    visual[coluna] = {'tipo': 'texto', 'valor': f'[BLOB — {len(valor)} bytes]'}
                else:
                    visual[coluna] = {'tipo': 'texto', 'valor': '' if valor is None else str(valor)}
            registros.append({'dados': registro, 'visual': visual})
        tabelas.append({'nome': nome, 'colunas': colunas, 'registros': registros})

    conexao.close()
    return render_template('banco.html', tabelas=tabelas, caminho_banco=BANCO)


@app.route('/admin/produtos')
def admin_produtos():

    if 'usuario' not in session:
        return redirect(url_for('index'))

    if session.get('tipo_usuario') != 'admin':
        flash("Acesso permitido somente para administradores.", "error")
        return redirect(url_for('ver_pedidos'))

    conexao = conectar()

    produtos = conexao.execute("""
        SELECT *
        FROM produtos
        ORDER BY categoria, sabor
    """).fetchall()

    conexao.close()

    return render_template(
        'admin_produtos.html',
        produtos=produtos
    )

@app.route('/admin/produtos/adicionar', methods=['POST'])
def adicionar_produto():

    if 'usuario' not in session:
        return redirect(url_for('index'))

    if session.get('tipo_usuario') != 'admin':
        flash("Acesso permitido somente para administradores.", "error")
        return redirect(url_for('index'))

    categoria = request.form.get('categoria')
    sabor = request.form.get('sabor')
    preco = request.form.get('preco')
    arquivo = request.files.get('foto')

    if not categoria or not sabor or not preco:
        flash("Preencha categoria, sabor e preço.", "error")
        return redirect(url_for('admin_produtos'))

    try:
        preco = float(preco)
    except ValueError:
        flash("Digite um preço válido.", "error")
        return redirect(url_for('admin_produtos'))

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO produtos
        (categoria, sabor, preco, foto)
        VALUES (?, ?, ?, ?)
    """, (
        categoria,
        sabor,
        preco,
        None
    ))

    produto_id = cursor.lastrowid

    if arquivo and arquivo.filename:

        if not arquivo_permitido(arquivo.filename):
            conexao.close()
            flash(
                "Formato inválido. Use PNG, JPG, JPEG, GIF ou WEBP.",
                "error"
            )
            return redirect(url_for('admin_produtos'))

        nome_seguro = secure_filename(arquivo.filename)
        extensao = nome_seguro.rsplit('.', 1)[1].lower()

        nome_foto = f"produto_{produto_id}.{extensao}"

        caminho = os.path.join(
            PASTA_PRODUTOS,
            nome_foto
        )

        arquivo.save(caminho)

        cursor.execute("""
            UPDATE produtos
            SET foto = ?
            WHERE id = ?
        """, (nome_foto, produto_id))

    conexao.commit()
    conexao.close()

    flash("Produto adicionado com sucesso!", "success")
    return redirect(url_for('admin_produtos'))

@app.route('/admin/produtos/<int:produto_id>/foto', methods=['POST'])
def admin_foto_produto(produto_id):

    if 'usuario' not in session:
        return redirect(url_for('index'))

    if session.get('tipo_usuario') != 'admin':
        flash("Acesso negado.", "error")
        return redirect(url_for('index'))

    arquivo = request.files.get('foto')

    if not arquivo or not arquivo.filename:
        flash("Selecione uma imagem.", "error")
        return redirect(url_for('admin_produtos'))

    if not arquivo_permitido(arquivo.filename):
        flash(
            "Formato inválido. Use PNG, JPG, JPEG, GIF ou WEBP.",
            "error"
        )
        return redirect(url_for('admin_produtos'))

    pasta_produtos = PASTA_PRODUTOS

    nome_seguro = secure_filename(arquivo.filename)

    extensao = nome_seguro.rsplit('.', 1)[1].lower()

    nome_foto = f"produto_{produto_id}.{extensao}"

    caminho = os.path.join(
        pasta_produtos,
        nome_foto
    )

    arquivo.save(caminho)

    conexao = conectar()

    conexao.execute("""
        UPDATE produtos
        SET foto = ?
        WHERE id = ?
    """, (nome_foto, produto_id))

    conexao.commit()
    conexao.close()

    flash("Foto do produto atualizada com sucesso!", "success")

    return redirect(url_for('admin_produtos'))

@app.route('/conquistas')
def conquistas():

    if 'usuario' not in session:
        return redirect(url_for('index'))

    if session.get('tipo_usuario') != 'cliente':
        flash("Somente clientes possuem conquistas.", "error")
        return redirect(url_for('ver_pedidos'))

    cliente_id = session['usuario']['id']

    categorias = [
        {
            'nome': 'Bolos',
            'categoria': 'bolo',
            'pasta': 'bolos'
        },
        {
            'nome': 'Tortas',
            'categoria': 'torta',
            'pasta': 'tortas'
        },
        {
            'nome': 'Cupcakes',
            'categoria': 'cupcake',
            'pasta': 'cupcakes'
        },
        {
            'nome': 'Docinhos',
            'categoria': 'docinhos',
            'pasta': 'docinhos'
        },
        {
            'nome': 'Salgadinhos',
            'categoria': 'salgadinhos',
            'pasta': 'salgadinhos'
        }
    ]

    conexao = conectar()

    compras = conexao.execute("""
        SELECT
            LOWER(item) AS categoria,
            SUM(quantidade) AS total
        FROM pedidos
        WHERE cliente_id = ?
        GROUP BY LOWER(item)
    """, (cliente_id,)).fetchall()

    conexao.close()

    compras_por_categoria = {
        compra['categoria']: compra['total']
        for compra in compras
    }

    conquistas_lista = []

    for categoria in categorias:

        total = compras_por_categoria.get(
            categoria['categoria'],
            0
        )

        if total < 5:
            nivel = 'Branca'
        elif total < 10:
            nivel = 'Bronze'
        elif total < 15:
            nivel = 'Prata'
        elif total < 20:
            nivel = 'Ouro'
        else:
            nivel = 'Azul'

        # As imagens reais ficam em static/conquistas/<pasta>/
        # com o padrão: bolo_branca.png, torta_ouro.png, etc.
        imagem = f"{categoria['pasta']}/{categoria['categoria']}_{nivel.lower()}.png"

        if total >= 20:
            progresso = 100
            faltam = 0
        else:
            progresso = (total % 5) * 20
            faltam = 5 - (total % 5)

        conquistas_lista.append({
            'nome': categoria['nome'],
            'total': total,
            'nivel': nivel,
            'imagem': imagem,
            'progresso': progresso,
            'faltam': faltam
        })

    return render_template(
        'conquistas.html',
        conquistas=conquistas_lista
    )

@app.route('/comprar', methods=['GET', 'POST'])
def comprar_web():

    if 'usuario' not in session:
        return redirect(url_for('index'))

    if session.get('tipo_usuario') == 'funcionario':
        return "Funcionários não realizam compras.", 403

    conexao = conectar()

    produtos = conexao.execute("""
        SELECT *
        FROM produtos
        ORDER BY categoria, sabor
    """).fetchall()
    if request.method == 'POST':
        tipo_pedido = request.form.get('tipo_pedido')
        produto_id = request.form.get('produto_id')

        produto = conexao.execute("""
            SELECT *
            FROM produtos
            WHERE id = ?
        """, (produto_id,)).fetchone()

        if not produto:
            conexao.close()
            flash("Produto inválido!", "error")
            return redirect(url_for('comprar_web'))

        preco_base = produto['preco']
        item = produto['categoria']
        sabor = produto['sabor']

        quantidade = int(
            request.form.get('quantidade', 1))

        preco_total = preco_base * quantidade
        taxa_entrega = 0
        endereco = None

        if tipo_pedido == 'delivery':
            taxa_entrega = 10
            preco_total += taxa_entrega
            endereco = request.form.get(
                'endereco_entrega')

        metodo_pagamento = request.form.get(
            'metodo_pagamento')

        if metodo_pagamento == 'pix':
            pagamento_info = (
                "Pix - Código: "
                + ''.join(
                    random.choices(
                        string.ascii_uppercase
                        + string.digits,
                        k=6)))

        else:
            pagamento_info = (metodo_pagamento.capitalize())

        conexao.execute("""
            INSERT INTO pedidos
            (cliente_id, tipo, item, sabor, quantidade, preco, status, data, pagamento_info, endereco, taxa_entrega, cor, confeito, papel_arroz, glace, pasta_americana, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session['usuario']['id'],
            tipo_pedido.capitalize(),
            item.capitalize(),
            sabor.capitalize(),
            quantidade,
            preco_total,
            'Recebido',
            datetime.now().strftime("%d/%m/%Y"),
            pagamento_info,
            endereco,
            taxa_entrega,
            request.form.get('cor'),
            request.form.get('confeito'),
            request.form.get('papel_arroz', ''),
            request.form.get('glace', ''),
            request.form.get('pasta_americana', ''),
            request.form.get('observacao', '')))
        conexao.commit()
        conexao.close()

        flash("Pedido realizado com sucesso!", "success")
        return redirect(url_for('ver_pedidos'))
    conexao.close()
    return render_template('comprar.html', produtos=produtos)

@app.route('/api/produtos_mais_comprados')
def api_produtos_mais_comprados():
    if 'usuario' not in session:
        return {}, 401

    if session.get('tipo_usuario') not in ['funcionario', 'admin']:
        return {}, 403

    conexao = conectar()

    resultados = conexao.execute("""
        SELECT item, SUM(quantidade) AS total
        FROM pedidos
        GROUP BY item
        ORDER BY total DESC
    """).fetchall()

    conexao.close()

    dados = {
        resultado['item']: resultado['total']
        for resultado in resultados
    }

    return dados

@app.route('/pedidos')
def ver_pedidos():
    if 'usuario' not in session:
        return redirect(url_for('index'))
    conexao = conectar()
    if session.get('tipo_usuario') == 'funcionario':

        pedidos_db = conexao.execute("""
            SELECT
                pedidos.*,
                clientes.nome AS cliente
            FROM pedidos
            JOIN clientes
                ON pedidos.cliente_id = clientes.id
            ORDER BY pedidos.id DESC""").fetchall()

    else:
        pedidos_db = conexao.execute("""
            SELECT
                pedidos.*,
                clientes.nome AS cliente
            FROM pedidos
            JOIN clientes
                ON pedidos.cliente_id = clientes.id
            WHERE pedidos.cliente_id = ?
            ORDER BY pedidos.id DESC
        """, (session['usuario']['id'],)).fetchall()

    conexao.close()
    pedidos = []

    for pedido in pedidos_db:
        pedidos.append({'cliente': pedido['cliente'], 'dados': dict(pedido)})
    return render_template('pedidos.html', pedidos=pedidos)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

criar_banco()
inserir_produtos()
sincronizar_fotos_produtos()

if __name__ == '__main__':
    app.run(debug=True)