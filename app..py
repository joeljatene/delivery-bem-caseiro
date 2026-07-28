import datetime
import urllib.parse
import psycopg2 
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import re
import warnings
import os
from streamlit_autorefresh import st_autorefresh

warnings.filterwarnings('ignore', category=UserWarning)

# ==========================================
# 0. CONFIGURAÇÕES E DADOS DO RESTAURANTE
# ==========================================
NUMERO_WHATSAPP = "5595981136537" 

TAXAS_ENTREGA = {
    "Retirar no Local": 0.00,
    "Centro": 5.00,
    "Mecejana": 6.00,
    "São Vicente": 6.00,
    "Caimbé": 7.00,
    "Buritis": 7.00,
    "Pintolândia": 10.00,
    "Cauamé": 12.00
}

# INICIALIZAÇÃO DAS VARIÁVEIS DE SESSÃO
if 'carrinho' not in st.session_state:
    st.session_state['carrinho'] = {}
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'motoboy_autenticado' not in st.session_state:
    st.session_state['motoboy_autenticado'] = False
if 'motoboy_nome' not in st.session_state:
    st.session_state['motoboy_nome'] = ""

# ==========================================
# 1. FUNÇÕES DE BANCO DE DADOS (PostgreSQL)
# ==========================================
def get_conexao():
    db_url = st.secrets["connections"]["supabase"]["url"]
    return psycopg2.connect(db_url)

def inicializar_banco():
    conn = get_conexao()
    c = conn.cursor()
    
    # Tabela Pedidos
    c.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id SERIAL PRIMARY KEY,
            data_hora TEXT,
            cliente TEXT,
            telefone TEXT,
            endereco TEXT,
            itens TEXT,
            total NUMERIC,
            pagamento TEXT,
            status TEXT,
            taxa_entrega NUMERIC,
            motoboy TEXT
        )
    ''')
    
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='pedidos' AND column_name='motoboy'")
    if not c.fetchone():
        c.execute("ALTER TABLE pedidos ADD COLUMN motoboy TEXT")
    
    # Tabela Cardápio
    c.execute('''
        CREATE TABLE IF NOT EXISTS cardapio (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            preco NUMERIC,
            disponivel INTEGER,
            imagem TEXT,
            categoria TEXT DEFAULT 'Alimentos'
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM cardapio")
    if c.fetchone()[0] == 0:
        itens_iniciais = [
            ("Marmita Executiva Tradicional", 22.00, 1, "https://images.unsplash.com/photo-1628296939923-d64e9a6e35cb?w=300&q=80", "Alimentos"),
            ("Prato Feito Especial", 28.00, 1, "https://images.unsplash.com/photo-1645696301019-35adcc18fc21?w=300&q=80", "Alimentos"),
            ("Suco Natural 500ml", 8.00, 1, "https://images.unsplash.com/photo-1622597467836-f38240662c8b?w=300&q=80", "Bebidas")
        ]
        c.executemany("INSERT INTO cardapio (nome, preco, disponivel, imagem, categoria) VALUES (%s, %s, %s, %s, %s)", itens_iniciais)

    # Tabela Clientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            telefone TEXT PRIMARY KEY,
            nome TEXT,
            bairro TEXT,
            endereco_rua TEXT
        )
    ''')
    
    # Tabela Motoboys
    c.execute('''
        CREATE TABLE IF NOT EXISTS motoboys (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            telefone TEXT,
            ativo INTEGER DEFAULT 1,
            senha TEXT
        )
    ''')
    
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='motoboys' AND column_name='senha'")
    if not c.fetchone():
        c.execute("ALTER TABLE motoboys ADD COLUMN senha TEXT")

    # Tabela Configurações
    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    config_iniciais = [('alarme_sonoro', 'ativado'), ('loja_aberta', 'ativado'), ('horario_auto', 'ativado')]
    for chave, valor in config_iniciais:
        c.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
        if not c.fetchone():
            c.execute("INSERT INTO configuracoes (chave, valor) VALUES (%s, %s)", (chave, valor))

    conn.commit()
    conn.close()

def get_config(chave):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 'ativado'

def set_config(chave, valor):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE configuracoes SET valor = %s WHERE chave = %s", (valor, chave))
    conn.commit()
    conn.close()

def buscar_cliente(telefone):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("SELECT nome, bairro, endereco_rua FROM clientes WHERE telefone = %s", (telefone,))
    resultado = c.fetchone()
    conn.close()
    return resultado

def salvar_cliente(telefone, nome, bairro, endereco_rua):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("SELECT telefone FROM clientes WHERE telefone = %s", (telefone,))
    if c.fetchone():
        c.execute("UPDATE clientes SET nome=%s, bairro=%s, endereco_rua=%s WHERE telefone=%s", (nome, bairro, endereco_rua, telefone))
    else:
        c.execute("INSERT INTO clientes (telefone, nome, bairro, endereco_rua) VALUES (%s, %s, %s, %s)", (telefone, nome, bairro, endereco_rua))
    conn.commit()
    conn.close()

def salvar_novo_pedido(cliente, telefone, endereco, itens, total, pagamento, taxa_entrega):
    conn = get_conexao()
    c = conn.cursor()
    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    itens_json = json.dumps(itens)
    
    c.execute('''
        INSERT INTO pedidos (data_hora, cliente, telefone, endereco, itens, total, pagamento, status, taxa_entrega)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (data_hora, cliente, telefone, endereco, itens_json, total, pagamento, 'Novo', taxa_entrega))
    
    pedido_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return pedido_id

def carregar_pedidos_ativos():
    conn = get_conexao()
    try:
        df = pd.read_sql_query("SELECT id, data_hora, cliente, telefone, endereco, itens, total, pagamento, status, taxa_entrega, motoboy FROM pedidos WHERE status NOT IN ('Concluído', 'Cancelado') ORDER BY id ASC", conn)
    except:
        df = pd.read_sql_query("SELECT *, '' as motoboy FROM pedidos WHERE status NOT IN ('Concluído', 'Cancelado') ORDER BY id ASC", conn)
    conn.close()
    return df

def atualizar_status_pedido(pedido_id, novo_status, motoboy=None):
    conn = get_conexao()
    c = conn.cursor()
    if motoboy:
        c.execute("UPDATE pedidos SET status = %s, motoboy = %s WHERE id = %s", (novo_status, motoboy, pedido_id))
    else:
        c.execute("UPDATE pedidos SET status = %s WHERE id = %s", (novo_status, pedido_id))
    conn.commit()
    conn.close()

def carregar_vendas_concluidas():
    conn = get_conexao()
    try:
        df = pd.read_sql_query("SELECT id, data_hora, cliente, telefone, endereco, itens, total, pagamento, status, taxa_entrega, motoboy FROM pedidos WHERE status = 'Concluído'", conn)
    except:
        df = pd.read_sql_query("SELECT *, '' as motoboy FROM pedidos WHERE status = 'Concluído'", conn)
    conn.close()
    return df

def carregar_cardapio_completo():
    conn = get_conexao()
    try:
        df = pd.read_sql_query("SELECT id, nome, preco, disponivel, imagem, categoria FROM cardapio ORDER BY disponivel DESC, id ASC", conn)
    except:
        df = pd.read_sql_query("SELECT *, 'Alimentos' as categoria FROM cardapio ORDER BY disponivel DESC, id ASC", conn)
    conn.close()
    return df.to_dict('records')

def adicionar_prato(nome, preco, imagem, categoria):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("INSERT INTO cardapio (nome, preco, disponivel, imagem, categoria) VALUES (%s, %s, 1, %s, %s)", (nome, preco, imagem, categoria))
    conn.commit()
    conn.close()

def atualizar_disponibilidade(prato_id, disponivel):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE cardapio SET disponivel = %s WHERE id = %s", (disponivel, prato_id))
    conn.commit()
    conn.close()

def excluir_prato(prato_id):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("DELETE FROM cardapio WHERE id = %s", (prato_id,))
    conn.commit()
    conn.close()

def editar_prato(prato_id, nome, preco, imagem, categoria):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE cardapio SET nome = %s, preco = %s, imagem = %s, categoria = %s WHERE id = %s", (nome, preco, imagem, categoria, prato_id))
    conn.commit()
    conn.close()

def carregar_motoboys(ativos_apenas=False):
    conn = get_conexao()
    if ativos_apenas:
        df = pd.read_sql_query("SELECT * FROM motoboys WHERE ativo = 1 ORDER BY nome", conn)
    else:
        df = pd.read_sql_query("SELECT * FROM motoboys ORDER BY ativo DESC, nome", conn)
    conn.close()
    return df.to_dict('records')

def adicionar_motoboy(nome, telefone, senha):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("INSERT INTO motoboys (nome, telefone, ativo, senha) VALUES (%s, %s, 1, %s)", (nome, telefone, senha))
    conn.commit()
    conn.close()

def editar_motoboy(moto_id, nome, telefone, senha):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE motoboys SET nome = %s, telefone = %s, senha = %s WHERE id = %s", (nome, telefone, senha, moto_id))
    conn.commit()
    conn.close()

def alternar_status_motoboy(motoboy_id, ativo):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE motoboys SET ativo = %s WHERE id = %s", (ativo, motoboy_id))
    conn.commit()
    conn.close()

def excluir_motoboy(motoboy_id):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("DELETE FROM motoboys WHERE id = %s", (motoboy_id,))
    conn.commit()
    conn.close()

try:
    inicializar_banco()
except Exception as e:
    st.error(f"Erro de conexão com o banco de dados Supabase: {e}")

# ==========================================
# 2. CONFIGURAÇÃO VISUAL E ROTEAMENTO
# ==========================================
st.set_page_config(page_title="Bem Caseiro Delivery", page_icon="🍲", layout="centered")

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        .stApp { background-color: #F7F9FC; }
        h1, h2, h3, h4, .stMarkdown p strong {
            color: #005753 !important;
            font-family: 'Helvetica Neue', sans-serif;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #F7F9FC; padding-bottom: 5px; }
        .stTabs [data-baseweb="tab"] { background-color: white; border-radius: 12px 12px 0 0; padding: 10px 24px; border: 1px solid #E0E6ED; border-bottom: none; color: #005753; font-weight: 600; }
        .stTabs [aria-selected="true"] { background-color: #005753 !important; color: white !important; border-color: #005753 !important; }
        .stButton > button { background-color: white; color: #F14C14 !important; border: 2px solid #F14C14 !important; border-radius: 12px !important; font-weight: 700 !important; padding: 8px 16px !important; transition: all 0.3s ease; width: 100%; }
        .stButton > button:hover { background-color: #F14C14 !important; color: white !important; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(241, 76, 20, 0.2); }
        button[kind="primary"] { background-color: #F14C14 !important; color: white !important; border: none !important; border-radius: 12px !important; padding: 20px !important; font-size: 18px !important; box-shadow: 0 4px 15px rgba(241, 76, 20, 0.3) !important; }
        button[kind="primary"]:hover { background-color: #D63E0E !important; box-shadow: 0 6px 20px rgba(214, 62, 14, 0.4) !important; }
        [data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] { background-color: white; padding: 20px; border-radius: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.04); margin-bottom: 12px; border: 1px solid #F0F2F5; }
    </style>
""", unsafe_allow_html=True)


is_admin = st.query_params.get("admin") == "sim"
is_motoboy = st.query_params.get("motoboy") == "sim"

# ROTEAMENTO E TELA DE LOGIN (ADMIN)
if is_admin:
    if not st.session_state['autenticado']:
        col_vazia1, col_logo, col_vazia2 = st.columns([1, 2, 1])
        with col_logo:
            if os.path.exists("logo.png"): st.image("logo.png", width="stretch")
            elif os.path.exists("image.png"): st.image("image.png", width="stretch")
            
        st.markdown("<h2 style='text-align: center;'>🔒 Acesso à Gestão</h2>", unsafe_allow_html=True)
        senha = st.text_input("Digite a senha de Gestão:", type="password")
        
        if st.button("Acessar Painel", type="primary"):
            senha_correta = st.secrets.get("admin_password", "152506")
            if senha == senha_correta:
                st.session_state['autenticado'] = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")
        st.stop() 

    st.sidebar.title("🔒 Gestão Bem Caseiro")
    if st.sidebar.button("Sair / Logout"):
        st.session_state['autenticado'] = False
        st.rerun()
        
    menu = st.sidebar.selectbox(
        "Navegação do Gestor", 
        [
            "Painel da Cozinha", 
            "Gestão do Cardápio", 
            "Gestão de Motoboys", 
            "Relatório Financeiro", 
            "Configurações"
        ]
    )

elif is_motoboy:
    menu = "Portal do Motoboy"
    st.markdown(
        """
        <style>
            [data-testid="collapsedControl"] {display: none;}
            [data-testid="stSidebar"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )
else:
    menu = "Fazer Pedido (Cliente)"
    st.markdown(
        """
        <style>
            [data-testid="collapsedControl"] {display: none;}
            [data-testid="stSidebar"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ==========================================
# VERIFICAÇÃO DE HORÁRIO DE FUNCIONAMENTO
# ==========================================
fuso_rr = datetime.timezone(datetime.timedelta(hours=-4)) # Fuso de Boa Vista
agora = datetime.datetime.now(fuso_rr)
dia_semana = agora.weekday() # 0 = Seg, ..., 5 = Sab, 6 = Dom
hora_atual = agora.time()

loja_aberta_manual = get_config('loja_aberta')
horario_auto = get_config('horario_auto')

loja_aberta = True
if loja_aberta_manual == 'desativado':
    loja_aberta = False
elif horario_auto == 'ativado':
    hora_abertura = datetime.time(10, 45)
    hora_fechamento = datetime.time(14, 30)
    if dia_semana == 6: # Domingo
        loja_aberta = False
    elif not (hora_abertura <= hora_atual <= hora_fechamento):
        loja_aberta = False

# ==========================================
# 3. MÓDULO DO CLIENTE (CARDÁPIO)
# ==========================================
if menu == "Fazer Pedido (Cliente)":
    
    col_vazia1, col_logo, col_vazia2 = st.columns([1, 2, 1])
    with col_logo:
        if os.path.exists("logo.png"): st.image("logo.png", width="stretch")
        elif os.path.exists("image.png"): st.image("image.png", width="stretch")
        else: st.markdown("<h1 style='text-align: center; color: #005753;'>Bem Caseiro Delivery</h1>", unsafe_allow_html=True)

    st.markdown("<h3 style='text-align: center;'>Faça o seu Pedido</h3>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center; color: #F14C14; font-size: 16px; font-weight: bold; margin-bottom: 20px; padding: 10px; background-color: white; border-radius: 10px; box-shadow: 0px 2px 5px rgba(0,0,0,0.05);'>⏱️ Tempo estimado de entrega: até 30 minutos</div>", unsafe_allow_html=True)

    if not loja_aberta:
        st.error("🛑 **ESTAMOS FECHADOS NO MOMENTO.**\n\nNosso horário de funcionamento é de **Segunda a Sábado, das 10:45 às 14:30**.")
        st.info("Você pode conferir as opções do cardápio abaixo, mas os botões de pedido estão temporariamente desativados.")

    try:
        cardapio_banco = carregar_cardapio_completo()
        itens_disponiveis = [item for item in cardapio_banco if item['disponivel'] == 1]
        
        if not itens_disponiveis:
            st.warning("Nosso cardápio está sendo atualizado no momento. Volte em alguns minutos!")
        else:
            aba_alimentos, aba_bebidas = st.tabs(["🍽️ Alimentos", "🥤 Bebidas"])

            with aba_alimentos:
                for item in itens_disponiveis:
                    if item.get("categoria", "Alimentos") != "Bebidas":
                        with st.container():
                            col_img, col_desc, col_add = st.columns([1.5, 3, 2])
                            with col_img:
                                if item.get("imagem"): st.image(item["imagem"], width="stretch") 
                            with col_desc:
                                st.markdown(f"**{item['nome']}**")
                                st.markdown(f"<span style='color: #005753; font-weight: bold; font-size: 16px;'>R$ {float(item['preco']):.2f}</span>", unsafe_allow_html=True)
                                obs_alim = st.text_input("Obs:", placeholder="Ex: sem cebola", key=f"obs_alim_{item['id']}")
                            with col_add:
                                qtd_desejada = st.number_input("Qtd", min_value=1, max_value=20, value=1, key=f"qtd_item_{item['id']}")
                                if loja_aberta:
                                    if st.button("Adicionar", key=f"btn_add_{item['id']}", use_container_width=True):
                                        nome_final = f"{item['nome']} [Obs: {obs_alim}]" if obs_alim else item['nome']
                                        chave_item = f"{item['id']}_{obs_alim}"
                                        if chave_item in st.session_state['carrinho']: st.session_state['carrinho'][chave_item]['qtd'] += qtd_desejada
                                        else: st.session_state['carrinho'][chave_item] = {"id": item['id'], "nome": nome_final, "preco": float(item['preco']), "qtd": qtd_desejada}
                                        st.toast(f"{qtd_desejada}x {item['nome']} adicionado!", icon="✅")
                                else:
                                    st.button("Fechado", key=f"btn_add_{item['id']}", disabled=True, use_container_width=True)

            with aba_bebidas:
                for item in itens_disponiveis:
                    if item.get("categoria") == "Bebidas":
                        with st.container():
                            col_img, col_desc, col_add = st.columns([1.5, 3, 2])
                            with col_img:
                                if item.get("imagem"): st.image(item["imagem"], width="stretch") 
                            with col_desc:
                                st.markdown(f"**{item['nome']}**")
                                st.markdown(f"<span style='color: #005753; font-weight: bold; font-size: 16px;'>R$ {float(item['preco']):.2f}</span>", unsafe_allow_html=True)
                                sabor = ""
                                if "Suco" in item['nome']: sabor = st.selectbox("Sabor:", ["Laranja", "Limão", "Maracujá", "Goiaba", "Cupuaçu"], key=f"sabor_{item['id']}")
                                elif "Refrigerante" in item['nome']: sabor = st.selectbox("Opção:", ["Coca-Cola", "Guaraná Antarctica", "Fanta Laranja", "Sprite", "Coca-Cola Zero"], key=f"sabor_{item['id']}")
                                obs_beb = st.text_input("Obs:", placeholder="Ex: sem açúcar", key=f"obs_beb_{item['id']}")
                            with col_add:
                                qtd_desejada = st.number_input("Qtd", min_value=1, max_value=20, value=1, key=f"qtd_item_beb_{item['id']}")
                                if loja_aberta:
                                    if st.button("Adicionar", key=f"btn_add_beb_{item['id']}", use_container_width=True):
                                        nome_com_sabor = f"{item['nome']} ({sabor})" if sabor else item['nome']
                                        nome_final = f"{nome_com_sabor} [Obs: {obs_beb}]" if obs_beb else nome_com_sabor
                                        chave_item = f"{item['id']}_{sabor}_{obs_beb}"
                                        if chave_item in st.session_state['carrinho']: st.session_state['carrinho'][chave_item]['qtd'] += qtd_desejada
                                        else: st.session_state['carrinho'][chave_item] = {"id": item['id'], "nome": nome_final, "preco": float(item['preco']), "qtd": qtd_desejada}
                                        st.toast(f"{qtd_desejada}x {nome_com_sabor} adicionado!", icon="✅")
                                else:
                                    st.button("Fechado", key=f"btn_add_beb_{item['id']}", disabled=True, use_container_width=True)

            if len(st.session_state['carrinho']) > 0:
                st.subheader("🛒 Resumo do Pedido")
                
                total_itens = 0.0
                carrinho_formatado_para_banco = []

                chaves_carrinho = list(st.session_state['carrinho'].keys())
                for chave in chaves_carrinho:
                    item_cart = st.session_state['carrinho'][chave]
                    subtotal = item_cart['qtd'] * item_cart['preco']
                    total_itens += subtotal
                    
                    carrinho_formatado_para_banco.append({"nome": item_cart['nome'], "qtd": item_cart['qtd'], "subtotal": subtotal})

                    with st.container():
                        col_nome, col_edit, col_del = st.columns([3, 1.5, 1])
                        with col_nome:
                            st.markdown(f"**{item_cart['nome']}**")
                            st.markdown(f"R$ {item_cart['preco']:.2f} un — **Total: R$ {subtotal:.2f}**")
                        with col_edit:
                            nova_qtd = st.number_input("Qtd", min_value=1, max_value=30, value=item_cart['qtd'], key=f"edit_qtd_{chave}")
                            if nova_qtd != item_cart['qtd']:
                                st.session_state['carrinho'][chave]['qtd'] = nova_qtd
                                st.rerun()
                        with col_del:
                            st.write("") 
                            if st.button("🗑️", key=f"del_cart_{chave}"):
                                del st.session_state['carrinho'][chave]
                                st.rerun()
                            
                st.markdown(f"<h3 style='text-align: right;'>Subtotal: R$ {total_itens:.2f}</h3>", unsafe_allow_html=True)
                st.write("---")

                st.subheader("🛵 Entrega e Pagamento")
                telefone_input = st.text_input("Seu WhatsApp (Somente números)", placeholder="Ex: 95999999999")
                
                cli_nome, cli_bairro, cli_rua, telefone_limpo = "", "Centro", "", ""

                if telefone_input:
                    telefone_limpo = re.sub(r'\D', '', telefone_input)
                    if len(telefone_limpo) >= 10:
                        cliente_dados = buscar_cliente(telefone_limpo)
                        if cliente_dados:
                            st.success("👋 Bem-vindo de volta! Preenchemos seus dados.")
                            cli_nome = cliente_dados[0]
                            cli_bairro = cliente_dados[1] if cliente_dados[1] in TAXAS_ENTREGA else "Centro"
                            cli_rua = cliente_dados[2]
                    else: st.warning("Digite o telefone completo com o DDD.")

                with st.form("form_cliente"):
                    nome_cliente = st.text_input("Nome Completo", value=cli_nome)
                    col_bairro, col_rua = st.columns([1, 2])
                    with col_bairro:
                        idx_bairro = list(TAXAS_ENTREGA.keys()).index(cli_bairro) if cli_bairro in TAXAS_ENTREGA else 0
                        bairro_selecionado = st.selectbox("Bairro", list(TAXAS_ENTREGA.keys()), index=idx_bairro)
                    with col_rua:
                        endereco_rua = st.text_input("Rua, Número e Referência", value=cli_rua)

                    pagamento = st.selectbox("Forma de Pagamento", ["Pix", "Cartão (Entrega)", "Dinheiro"])
                    troco = st.text_input("Troco para quanto? (Se for dinheiro)")

                    st.write("") 
                    
                    if loja_aberta:
                        enviar = st.form_submit_button("Finalizar Pedido via WhatsApp", type="primary", use_container_width=True)
                    else:
                        enviar = st.form_submit_button("Restaurante Fechado", disabled=True, use_container_width=True)

                    if enviar:
                        if telefone_limpo and nome_cliente and carrinho_formatado_para_banco and (endereco_rua or bairro_selecionado == "Retirar no Local"):
                            valor_frete = TAXAS_ENTREGA[bairro_selecionado]
                            endereco_completo = f"{bairro_selecionado} - {endereco_rua}" if bairro_selecionado != "Retirar no Local" else "Retirada no Local"
                            total_geral = total_itens + valor_frete
                            pagamento_formatado = f"{pagamento} (Troco: R$ {troco})" if pagamento == "Dinheiro" and troco else pagamento
                            
                            salvar_cliente(telefone_limpo, nome_cliente, bairro_selecionado, endereco_rua)
                            pedido_id = salvar_novo_pedido(nome_cliente, telefone_limpo, endereco_completo, carrinho_formatado_para_banco, total_geral, pagamento_formatado, valor_frete)

                            texto_pedido = f"Olá, Bem Caseiro! Gostaria de confirmar meu pedido #{pedido_id}:\n\n👤 *Cliente:* {nome_cliente}\n📱 *Contato:* {telefone_limpo}\n📍 *Endereço:* {endereco_completo}\n\n*Itens do Pedido:*\n"
                            for item in carrinho_formatado_para_banco: texto_pedido += f"- {item['qtd']}x {item['nome']} (R$ {item['subtotal']:.2f})\n"
                            texto_pedido += f"\n📦 *Subtotal:* R$ {total_itens:.2f}\n🛵 *Taxa de Entrega:* R$ {valor_frete:.2f}\n💰 *Total Geral:* R$ {total_geral:.2f}\n💳 *Pagamento:* {pagamento_formatado}"

                            link_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP}?text={urllib.parse.quote(texto_pedido)}"
                            st.session_state['carrinho'] = {}
                            st.success(f"✅ Pedido #{pedido_id} registrado! Valor Total: R$ {total_geral:.2f}.")
                            st.markdown(f'<a href="{link_whatsapp}" target="_blank" style="display: block; padding: 15px 20px; background-color: #25D366; color: white; text-align: center; text-decoration: none; font-size: 18px; font-weight: bold; border-radius: 12px; margin-top: 15px;">📱 Enviar Pedido para o Restaurante</a>', unsafe_allow_html=True)
                        else: st.error("Por favor, preencha os dados de entrega obrigatórios.")

    except Exception as e:
        st.error(f"Erro de comunicação com o sistema: {e}")

# ==========================================
# 4. PORTAL DO MOTOBOY (LOGIN E LISTAGEM)
# ==========================================
elif menu == "Portal do Motoboy":
    
    col_vazia1, col_logo, col_vazia2 = st.columns([1, 2, 1])
    with col_logo:
        if os.path.exists("logo.png"): st.image("logo.png", width="stretch")
        elif os.path.exists("image.png"): st.image("image.png", width="stretch")
        
    st.markdown("<h2 style='text-align: center; color: #F14C14;'>🛵 Portal do Entregador</h2>", unsafe_allow_html=True)
    
    if not st.session_state['motoboy_autenticado']:
        motoboys_ativos = carregar_motoboys(ativos_apenas=True)
        if not motoboys_ativos:
            st.warning("Nenhum entregador cadastrado ou ativo no momento.")
        else:
            lista_nomes = [m['nome'] for m in motoboys_ativos]
            dict_senhas = {m['nome']: m.get('senha', '1234') for m in motoboys_ativos} 
            
            with st.container():
                st.info("Selecione seu nome e digite a sua senha para ver suas entregas.")
                nome_selecionado = st.selectbox("Seu Nome:", ["Selecione..."] + lista_nomes)
                senha_digitada = st.text_input("Sua Senha:", type="password")
                
                if st.button("Acessar minhas entregas", type="primary", use_container_width=True):
                    if nome_selecionado != "Selecione...":
                        senha_correta = dict_senhas.get(nome_selecionado)
                        if not senha_correta: 
                            senha_correta = "1234"
                            
                        if senha_digitada == senha_correta:
                            st.session_state['motoboy_autenticado'] = True
                            st.session_state['motoboy_nome'] = nome_selecionado
                            st.rerun()
                        else:
                            st.error("Senha incorreta! (A senha padrão é 1234 se não foi alterada).")
                    else:
                        st.warning("Por favor, selecione seu nome na lista.")
        st.stop() 
        
    st_autorefresh(interval=15000, limit=None, key="atualizacao_portal_motoboy")
    
    nome_motoboy_logado = st.session_state['motoboy_nome']
    
    col_info, col_sair = st.columns([3, 1])
    with col_info: st.success(f"Logado como: **{nome_motoboy_logado}**")
    with col_sair:
        if st.button("Sair"):
            st.session_state['motoboy_autenticado'] = False
            st.session_state['motoboy_nome'] = ""
            st.rerun()

    st.divider()
    st.subheader("Suas Entregas em Andamento:")
    
    df_pedidos = carregar_pedidos_ativos()
    df_entregas = df_pedidos[(df_pedidos['status'] == 'Saiu para Entrega') & (df_pedidos['motoboy'] == nome_motoboy_logado)]
    
    if df_entregas.empty:
        st.info("Nenhuma entrega pendente para você. Aguarde na base! ☕")
    else:
        for index, row in df_entregas.iterrows():
            with st.container():
                st.markdown(f"### Pedido #{row['id']}")
                st.markdown(f"**👤 Cliente:** {row['cliente']}")
                st.markdown(f"**📍 Endereço:** {row['endereco']}")
                st.markdown(f"**💰 Receber:** R$ {float(row['total']):.2f} - Forma: **{row['pagamento']}**")
                
                with st.popover("✅ Confirmar Entrega Realizada", use_container_width=True):
                    st.markdown("Tem certeza que finalizou esta entrega?")
                    if st.button("Sim, confirmar entrega", key=f"conf_motoboy_{row['id']}", type="primary", use_container_width=True):
                        atualizar_status_pedido(row['id'], "Concluído", nome_motoboy_logado)
                        st.success("Entrega finalizada com sucesso! A cozinha foi avisada.")
                        st.rerun()

# ==========================================
# 5. GESTÃO DO CARDÁPIO
# ==========================================
elif menu == "Gestão do Cardápio":
    st.title("📝 Gestão do Cardápio")
    with st.expander("➕ Cadastrar Novo Item", expanded=False):
        with st.form("form_novo_prato", clear_on_submit=True):
            novo_nome = st.text_input("Nome do Prato/Bebida*")
            novo_preco = st.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=1.0)
            nova_categoria = st.selectbox("Categoria", ["Alimentos", "Bebidas"])
            nova_imagem = st.text_input("Link da Imagem (Opcional)")
            if st.form_submit_button("Salvar no Cardápio"):
                if novo_nome and novo_preco > 0:
                    adicionar_prato(novo_nome, novo_preco, nova_imagem, nova_categoria)
                    st.success(f"'{novo_nome}' adicionado!")
                    st.rerun()
                else: st.error("Preencha nome e preço.")

    st.divider()
    st.subheader("Itens Cadastrados")
    cardapio_banco = carregar_cardapio_completo()
    if not cardapio_banco: st.info("Nenhum item cadastrado.")
    else:
        for item in cardapio_banco:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.write(f"**{item['nome']}** ({item.get('categoria', 'Alimentos')})")
                c2.write(f"R$ {float(item['preco']):.2f}")
                is_ativo = bool(item['disponivel'])
                toggle_ativo = c3.toggle("Ativo", value=is_ativo, key=f"tgl_{item['id']}")
                if toggle_ativo != is_ativo:
                    atualizar_disponibilidade(item['id'], int(toggle_ativo))
                    st.rerun()
                if c4.button("🗑️", key=f"del_{item['id']}"):
                    excluir_prato(item['id'])
                    st.rerun()
                with st.expander(f"✏️ Editar", expanded=False):
                    with st.form(f"form_edit_{item['id']}"):
                        edit_nome = st.text_input("Nome", value=item['nome'])
                        edit_preco = st.number_input("Preço (R$)", min_value=0.0, value=float(item['preco']), format="%.2f", step=1.0)
                        cat_atual = item.get('categoria', 'Alimentos')
                        idx_cat = 1 if cat_atual == "Bebidas" else 0
                        edit_categoria = st.selectbox("Categoria", ["Alimentos", "Bebidas"], index=idx_cat, key=f"edit_cat_{item['id']}")
                        edit_imagem = st.text_input("Link da Imagem", value=item['imagem'] if item['imagem'] else "")
                        if st.form_submit_button("Salvar Alterações"):
                            if edit_nome and edit_preco > 0:
                                editar_prato(item['id'], edit_nome, edit_preco, edit_imagem, edit_categoria)
                                st.success("Atualizado!")
                                st.rerun()

# ==========================================
# 6. GESTÃO DE MOTOBOYS
# ==========================================
elif menu == "Gestão de Motoboys":
    st.title("🛵 Gestão de Motoboys")

    with st.expander("➕ Cadastrar Novo Motoboy", expanded=False):
        with st.form("form_novo_motoboy", clear_on_submit=True):
            nome_motoboy = st.text_input("Nome do Entregador*")
            tel_motoboy = st.text_input("Telefone/WhatsApp")
            senha_motoboy = st.text_input("Senha de Acesso ao App*", type="password", placeholder="Ex: 1234")
            
            if st.form_submit_button("Salvar Motoboy"):
                if nome_motoboy and senha_motoboy:
                    adicionar_motoboy(nome_motoboy, tel_motoboy, senha_motoboy)
                    st.success(f"Motoboy '{nome_motoboy}' cadastrado com sucesso!")
                    st.rerun()
                else:
                    st.error("O nome e a senha são obrigatórios.")

    st.divider()
    st.subheader("Equipe de Entrega")
    lista_motoboys_banco = carregar_motoboys(ativos_apenas=False)
    
    if not lista_motoboys_banco:
        st.info("Nenhum motoboy cadastrado. Adicione sua equipe acima.")
    else:
        for moto in lista_motoboys_banco:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                c1.write(f"**{moto['nome']}**")
                c2.write(f"{moto['telefone']}")
                
                is_ativo = bool(moto['ativo'])
                toggle_ativo = c3.toggle("Ativo", value=is_ativo, key=f"tgl_moto_{moto['id']}")
                if toggle_ativo != is_ativo:
                    alternar_status_motoboy(moto['id'], int(toggle_ativo))
                    st.rerun()
                    
                if c4.button("🗑️", key=f"del_moto_{moto['id']}"):
                    excluir_motoboy(moto['id'])
                    st.rerun()
                    
                with st.expander("✏️ Editar/Trocar Senha", expanded=False):
                    with st.form(f"form_edit_moto_{moto['id']}"):
                        edit_nome_moto = st.text_input("Nome", value=moto['nome'])
                        edit_tel_moto = st.text_input("Telefone", value=moto['telefone'])
                        edit_senha_moto = st.text_input("Nova Senha", value=moto.get('senha', '1234'))
                        
                        if st.form_submit_button("Salvar Alterações"):
                            editar_motoboy(moto['id'], edit_nome_moto, edit_tel_moto, edit_senha_moto)
                            st.success("Dados do entregador atualizados!")
                            st.rerun()

# ==========================================
# 7. CONFIGURAÇÕES DO SISTEMA
# ==========================================
elif menu == "Configurações":
    st.title("⚙️ Configurações do Sistema")
    st.write("Ajuste as preferências de funcionamento do painel gerencial.")
    
    st.subheader("Controle de Expediente")
    
    status_manual = get_config('loja_aberta')
    is_manual_on = True if status_manual == 'ativado' else False
    novo_status_manual = st.toggle("🏪 Loja Aberta (Desative para fechar o delivery em imprevistos ou feriados)", value=is_manual_on)
    novo_val_manual = 'ativado' if novo_status_manual else 'desativado'
    
    if novo_val_manual != status_manual:
        set_config('loja_aberta', novo_val_manual)
        st.success("Status de abertura da loja atualizado!")
        st.rerun()

    status_auto = get_config('horario_auto')
    is_auto_on = True if status_auto == 'ativado' else False
    novo_status_auto = st.toggle("🕒 Seguir Horário Automático (Seg a Sáb, 10:45 às 14:30)", value=is_auto_on)
    novo_val_auto = 'ativado' if novo_status_auto else 'desativado'
    
    if novo_val_auto != status_auto:
        set_config('horario_auto', novo_val_auto)
        st.success("Configuração de horário automático atualizada!")
        st.rerun()
        
    st.divider()

    st.subheader("Notificações e Alertas")
    status_atual_alarme = get_config('alarme_sonoro')
    is_alarme_on = True if status_atual_alarme == 'ativado' else False
    novo_status_alarme = st.toggle("🔔 Tocar alarme sonoro quando chegar um Novo Pedido", value=is_alarme_on)
    novo_valor_bd = 'ativado' if novo_status_alarme else 'desativado'
    
    if novo_valor_bd != status_atual_alarme:
        set_config('alarme_sonoro', novo_valor_bd)
        st.success(f"Preferência de alarme atualizada para: **{novo_valor_bd.upper()}**!")
        st.rerun()

# ==========================================
# 8. MÓDULO DA COZINHA E FINANCEIRO
# ==========================================
elif menu == "Painel da Cozinha":
    st_autorefresh(interval=15000, limit=None, key="atualizacao_cozinha")
    st.title("📋 Painel da Cozinha")
    df_pedidos = carregar_pedidos_ativos()
    motoboys_ativos = carregar_motoboys(ativos_apenas=True)
    lista_nomes_motoboys = ["Não vinculado / Retirada"] + [m['nome'] for m in motoboys_ativos]

    if df_pedidos.empty: st.info("A cozinha está limpa! Aguardando novos pedidos...")
    else:
        tem_novo = any(df_pedidos['status'] == 'Novo')
        status_alarme = get_config('alarme_sonoro')
        if tem_novo:
            if status_alarme == 'ativado':
                st.error("🔔 **NOVO PEDIDO RECEBIDO!**")
                alerta_html = """
                    <audio id="alarme_bemcaseiro" autoplay loop>
                        <source src="https://cdn.pixabay.com/download/audio/2021/08/04/audio_0625c1539c.mp3?filename=success-1-6297.mp3" type="audio/mpeg">
                    </audio>
                    <script>
                        var audio = document.getElementById("alarme_bemcaseiro");
                        audio.play().catch(function(error) { console.log("Áudio bloqueado pelo navegador."); });
                    </script>
                """
                components.html(alerta_html, width=0, height=0)

        for index, row in df_pedidos.iterrows():
            status_atual = row['status']
            if status_atual == 'Novo': cor_fundo, cor_texto, emoji = "#FF4B4B", "white", "🔴"
            elif status_atual == 'Em Produção': cor_fundo, cor_texto, emoji = "#FFA500", "black", "🟡"
            elif status_atual == 'Saiu para Entrega': cor_fundo, cor_texto, emoji = "#005753", "white", "🟢"
            else: cor_fundo, cor_texto, emoji = "#808080", "white", "⚪"
                
            with st.expander(f"{emoji} Pedido #{row['id']} — {row['cliente']} — {status_atual.upper()}", expanded=True):
                st.markdown(f"<div style='background-color: {cor_fundo}; color: {cor_texto}; padding: 8px; border-radius: 5px; text-align: center; font-weight: bold; font-size: 16px; margin-bottom: 15px;'>STATUS: {status_atual.upper()}</div>", unsafe_allow_html=True)
                st.markdown(f"**WhatsApp:** {row.get('telefone', '')} | **Pagamento:** {row['pagamento']}")
                st.markdown(f"**Endereço:** {row['endereco']}")
                if row.get('motoboy') and row['motoboy'] != "Não vinculado / Retirada": st.markdown(f"🛵 **Entregador:** {row['motoboy']}")
                
                itens = json.loads(row['itens'])
                for i in itens: st.text(f"- {i['qtd']}x {i['nome']} (R$ {float(i['subtotal']):.2f})")
                
                taxa = float(row.get('taxa_entrega', 0.0))
                st.markdown(f"**Total (com frete): R$ {float(row['total']):.2f}**")

                tel_cliente = re.sub(r'\D', '', str(row.get('telefone', '')))
                if len(tel_cliente) >= 10:
                    if not tel_cliente.startswith('55'): tel_cliente = '55' + tel_cliente
                    mensagens_status = {
                        "Novo": f"Olá {row['cliente']}! Recebemos seu pedido #{row['id']} no Bem Caseiro. Em breve começaremos a preparar! 🍲",
                        "Em Produção": f"Olá {row['cliente']}! Seu pedido #{row['id']} já está na nossa cozinha sendo preparado com muito carinho! 👨‍🍳",
                        "Saiu para Entrega": f"Opa {row['cliente']}! O seu pedido #{row['id']} acabou de sair para entrega. O motoboy já está a caminho! 🛵💨"
                    }
                    if mensagens_status.get(row['status'], ""):
                        st.markdown(f'<a href="https://wa.me/{tel_cliente}?text={urllib.parse.quote(mensagens_status.get(row["status"], ""))}" target="_blank" style="display: block; margin-bottom: 15px; padding: 10px; background-color: #25D366; color: white; font-weight: bold; text-align: center; text-decoration: none; border-radius: 8px;">📲 Notificar Cliente no WhatsApp</a>', unsafe_allow_html=True)

                with st.popover("🖨️ Imprimir Cupom"):
                    itens_html = "".join([f"{i['qtd']}x {i['nome']} <br>&nbsp;&nbsp;R$ {float(i['subtotal']):.2f}<br>" for i in itens])
                    cupom_html = f"<html><head><style>body {{ font-family: monospace; font-size: 14px; margin: 0; padding: 10px; color: #000; background: #fff; }} .center {{ text-align: center; }} .linha {{ border-bottom: 1px dashed #000; margin: 10px 0; }} .btn-imprimir {{ display: block; width: 100%; padding: 10px; margin-top: 15px; background: #000; color: #fff; border: none; cursor: pointer; font-weight: bold; }} @media print {{ .btn-imprimir {{ display: none; }} }}</style></head><body><div class='center'><strong>BEM CASEIRO DELIVERY</strong><br>Pedido #{row['id']}<br>Data: {row['data_hora']}</div><div class='linha'></div><strong>Cliente:</strong> {row['cliente']}<br><strong>Tel:</strong> {row['telefone']}<br><strong>End:</strong> {row['endereco']}<br><div class='linha'></div><strong>ITENS:</strong><br>{itens_html}<div class='linha'></div><strong>Subtotal:</strong> R$ {float(row['total']) - taxa:.2f}<br><strong>Frete:</strong> R$ {taxa:.2f}<br><strong>TOTAL: R$ {float(row['total']):.2f}</strong><br><strong>Pgto:</strong> {row['pagamento']}<br><div class='linha'></div><button class='btn-imprimir' onclick='window.print()'>🖨️ CLIQUE AQUI PARA IMPRIMIR</button></body></html>"
                    components.html(cupom_html, height=450, scrolling=True)

                motoboy_selecionado = st.selectbox("Vincular Motoboy:", lista_nomes_motoboys, key=f"sel_moto_{row['id']}")

                col1, col2, col3, col4 = st.columns(4)
                if col1.button("Produção", key=f"prod_{row['id']}", use_container_width=True): 
                    atualizar_status_pedido(row['id'], "Em Produção", motoboy_selecionado)
                    st.rerun()
                if col2.button("Entrega", key=f"ent_{row['id']}", use_container_width=True): 
                    atualizar_status_pedido(row['id'], "Saiu para Entrega", motoboy_selecionado)
                    st.rerun()
                    
                with col3.popover("✅ Concluir", use_container_width=True):
                    st.markdown("**Confirmar conclusão?**")
                    if st.button("Sim, concluir", key=f"conf_conc_{row['id']}", type="primary", use_container_width=True):
                        atualizar_status_pedido(row['id'], "Concluído", motoboy_selecionado)
                        st.rerun()
                        
                with col4.popover("❌ Cancelar", use_container_width=True):
                    st.markdown("**Confirmar cancelamento?**")
                    if st.button("Sim, cancelar", key=f"conf_canc_{row['id']}", type="primary", use_container_width=True):
                        atualizar_status_pedido(row['id'], "Cancelado")
                        st.rerun()

elif menu == "Relatório Financeiro":
    st.title("📊 Relatório Financeiro")
    df_vendas = carregar_vendas_concluidas()

    if df_vendas.empty: st.warning("Nenhuma venda concluída.")
    else:
        df_vendas['total'] = df_vendas['total'].astype(float)
        df_vendas['taxa_entrega'] = df_vendas['taxa_entrega'].astype(float) if 'taxa_entrega' in df_vendas.columns else 0.0
        df_vendas['data_hora_dt'] = pd.to_datetime(df_vendas['data_hora'], format="%d/%m/%Y %H:%M:%S", errors='coerce')
        
        col_data1, col_data2 = st.columns(2)
        hoje = datetime.date.today()
        data_inicio = col_data1.date_input("Data Inicial", hoje)
        data_fim = col_data2.date_input("Data Final", hoje)
        
        mask = (df_vendas['data_hora_dt'].dt.date >= data_inicio) & (df_vendas['data_hora_dt'].dt.date <= data_fim)
        df_vendas_filtrado = df_vendas.loc[mask]
        
        if df_vendas_filtrado.empty: st.info("Nenhuma venda concluída para o período selecionado.")
        else:
            faturamento_total = df_vendas_filtrado['total'].sum()
            total_fretes = df_vendas_filtrado['taxa_entrega'].sum()
            faturamento_produtos = faturamento_total - total_fretes
            qtd_pedidos = len(df_vendas_filtrado)
            ticket_medio = faturamento_total / qtd_pedidos if qtd_pedidos > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Faturamento Bruto", f"R$ {faturamento_total:,.2f}")
            col2.metric("Só Produtos", f"R$ {faturamento_produtos:,.2f}")
            col3.metric("Total Fretes", f"R$ {total_fretes:,.2f}")
            col4.metric("Ticket Médio", f"R$ {ticket_medio:,.2f}")

            st.divider()
            st.subheader("🛵 Acerto dos Motoboys (Período)")
            df_entregas = df_vendas_filtrado[(df_vendas_filtrado['motoboy'].notna()) & (df_vendas_filtrado['motoboy'] != '') & (df_vendas_filtrado['motoboy'] != 'Não vinculado / Retirada')]
            if df_entregas.empty: st.info("Nenhum pedido vinculado a motoboy neste período.")
            else:
                acerto_motoboys = df_entregas.groupby('motoboy').agg(Corridas=('id', 'count'), Total_Taxas=('taxa_entrega', 'sum')).reset_index()
                acerto_motoboys.rename(columns={'motoboy': 'Entregador', 'Total_Taxas': 'Valor a Pagar (R$)'}, inplace=True)
                st.dataframe(acerto_motoboys, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("📋 Histórico Detalhado")
            colunas_exibicao = ['id', 'data_hora', 'cliente', 'motoboy', 'pagamento', 'total']
            if 'motoboy' not in df_vendas_filtrado.columns: df_vendas_filtrado['motoboy'] = ""
            df_exibicao = df_vendas_filtrado[colunas_exibicao].copy()
            df_exibicao.rename(columns={'id': 'Pedido', 'data_hora': 'Data/Hora', 'cliente': 'Cliente', 'motoboy': 'Entregador', 'pagamento': 'Pagamento', 'total': 'Total (R$)'}, inplace=True)
            st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
            st.download_button(label="📥 Baixar em CSV", data=df_exibicao.to_csv(index=False).encode('utf-8'), file_name=f"relatorio_vendas_{data_inicio}_a_{data_fim}.csv", mime="text/csv", type="primary")