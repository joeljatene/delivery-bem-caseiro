import datetime
import urllib.parse
import psycopg2 # Novo driver para o banco em nuvem
import json
import pandas as pd
import streamlit as st
import re
import warnings

# Oculta avisos do Pandas sobre conexões diretas
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

# ==========================================
# 1. FUNÇÕES DE BANCO DE DADOS (PostgreSQL)
# ==========================================
def get_conexao():
    # Puxa o link seguro do cofre do Streamlit
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def inicializar_banco():
    conn = get_conexao()
    c = conn.cursor()
    
    # Criação das Tabelas no padrão PostgreSQL
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
            taxa_entrega NUMERIC
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS cardapio (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            preco NUMERIC,
            disponivel INTEGER,
            imagem TEXT
        )
    ''')
    
    # Popula cardápio inicial se estiver vazio
    c.execute("SELECT COUNT(*) FROM cardapio")
    if c.fetchone()[0] == 0:
        itens_iniciais = [
            ("Marmita Executiva Tradicional", 22.00, 1, "https://images.unsplash.com/photo-1628296939923-d64e9a6e35cb?w=300&q=80"),
            ("Prato Feito Especial", 28.00, 1, "https://images.unsplash.com/photo-1645696301019-35adcc18fc21?w=300&q=80"),
            ("Suco Natural 500ml", 8.00, 1, "https://images.unsplash.com/photo-1622597467836-f38240662c8b?w=300&q=80")
        ]
        # No Postgres, os parâmetros usam %s em vez de ?
        c.executemany("INSERT INTO cardapio (nome, preco, disponivel, imagem) VALUES (%s, %s, %s, %s)", itens_iniciais)

    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            telefone TEXT PRIMARY KEY,
            nome TEXT,
            bairro TEXT,
            endereco_rua TEXT
        )
    ''')

    conn.commit()
    conn.close()

# --- Funções de Clientes ---
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

# --- Funções de Pedidos e Cardápio ---
def salvar_novo_pedido(cliente, telefone, endereco, itens, total, pagamento, taxa_entrega):
    conn = get_conexao()
    c = conn.cursor()
    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    itens_json = json.dumps(itens)
    
    # O Postgres exige a cláusula RETURNING id para devolver o número do pedido recém-criado
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
    df = pd.read_sql_query("SELECT * FROM pedidos WHERE status NOT IN ('Concluído', 'Cancelado') ORDER BY id ASC", conn)
    conn.close()
    return df

def atualizar_status_pedido(pedido_id, novo_status):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE pedidos SET status = %s WHERE id = %s", (novo_status, pedido_id))
    conn.commit()
    conn.close()

def carregar_vendas_concluidas():
    conn = get_conexao()
    df = pd.read_sql_query("SELECT * FROM pedidos WHERE status = 'Concluído'", conn)
    conn.close()
    return df

def carregar_cardapio_completo():
    conn = get_conexao()
    df = pd.read_sql_query("SELECT * FROM cardapio ORDER BY disponivel DESC, id ASC", conn)
    conn.close()
    return df.to_dict('records')

def adicionar_prato(nome, preco, imagem):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("INSERT INTO cardapio (nome, preco, disponivel, imagem) VALUES (%s, %s, 1, %s)", (nome, preco, imagem))
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

def editar_prato(prato_id, nome, preco, imagem):
    conn = get_conexao()
    c = conn.cursor()
    c.execute("UPDATE cardapio SET nome = %s, preco = %s, imagem = %s WHERE id = %s", (nome, preco, imagem, prato_id))
    conn.commit()
    conn.close()

try:
    inicializar_banco()
except Exception as e:
    st.error(f"Erro de conexão com o banco de dados: {e}")

# ==========================================
# 2. CONFIGURAÇÃO E ROTEAMENTO
# ==========================================
st.set_page_config(page_title="Bem Caseiro Delivery", page_icon="🍲", layout="wide")

is_admin = st.query_params.get("admin") == "sim"

if is_admin:
    st.sidebar.title("🔒 Gestão Bem Caseiro")
    menu = st.sidebar.selectbox(
        "Navegação do Gestor", 
        ["Painel da Cozinha / Gestão", "Gestão do Cardápio", "Relatório Financeiro", "Fazer Pedido (Cliente)"]
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
# 3. MÓDULO DO CLIENTE (CARDÁPIO)
# ==========================================
if menu == "Fazer Pedido (Cliente)":
    st.title("🍽️ Bem Caseiro - Faça o seu Pedido")
    st.subheader("Nosso Cardápio:")

    carrinho = []
    total_itens = 0.0

    cardapio_banco = carregar_cardapio_completo()
    itens_disponiveis = [item for item in cardapio_banco if item['disponivel'] == 1]
    
    if not itens_disponiveis:
        st.warning("Nosso cardápio está sendo atualizado no momento. Volte em alguns minutos!")
    else:
        for item in itens_disponiveis:
            with st.container():
                col_img, col_desc, col_qtd = st.columns([1, 3, 1])
                with col_img:
                    if item.get("imagem"):
                        st.image(item["imagem"], use_container_width=True)
                with col_desc:
                    st.markdown(f"**{item['nome']}**")
                    st.markdown(f"R$ {float(item['preco']):.2f}")
                with col_qtd:
                    qtd = st.number_input("Quantidade", min_value=0, max_value=20, value=0, key=f"item_cli_{item['id']}")
                    if qtd > 0:
                        subtotal = qtd * float(item['preco'])
                        carrinho.append({"nome": item["nome"], "qtd": qtd, "subtotal": subtotal})
                        total_itens += subtotal
            st.divider()

        st.markdown(f"### Subtotal dos itens: R$ {total_itens:.2f}")
        st.divider()

        st.subheader("Dados para Entrega")
        
        telefone_input = st.text_input("Seu WhatsApp (Digite apenas números e clique fora)", placeholder="Ex: 95999999999")
        
        cli_nome = ""
        cli_bairro = "Centro"
        cli_rua = ""
        telefone_limpo = ""

        if telefone_input:
            telefone_limpo = re.sub(r'\D', '', telefone_input)
            if len(telefone_limpo) >= 10:
                cliente_dados = buscar_cliente(telefone_limpo)
                if cliente_dados:
                    st.success("👋 Encontramos seu cadastro! Preenchemos seus dados para adiantar.")
                    cli_nome = cliente_dados[0]
                    cli_bairro = cliente_dados[1] if cliente_dados[1] in TAXAS_ENTREGA else "Centro"
                    cli_rua = cliente_dados[2]
                else:
                    st.info("Primeira vez por aqui? Preencha os dados abaixo que já deixaremos salvo para a próxima.")
            else:
                st.warning("Digite o telefone completo com o DDD.")

        with st.form("form_cliente"):
            nome_cliente = st.text_input("Nome Completo", value=cli_nome)
            
            col_bairro, col_rua = st.columns([1, 2])
            with col_bairro:
                idx_bairro = list(TAXAS_ENTREGA.keys()).index(cli_bairro) if cli_bairro in TAXAS_ENTREGA else 0
                bairro_selecionado = st.selectbox("Bairro", list(TAXAS_ENTREGA.keys()), index=idx_bairro)
                
            with col_rua:
                endereco_rua = st.text_input("Rua, Número e Ponto de Referência", value=cli_rua)

            pagamento = st.selectbox("Forma de Pagamento", ["Pix", "Cartão (Entrega)", "Dinheiro"])
            troco = st.text_input("Troco para quanto? (Se for dinheiro)")

            st.write("") 
            enviar = st.form_submit_button("Finalizar e Enviar para o WhatsApp", type="primary", use_container_width=True)

            if enviar:
                if telefone_limpo and nome_cliente and carrinho and (endereco_rua or bairro_selecionado == "Retirar no Local"):
                    
                    valor_frete = TAXAS_ENTREGA[bairro_selecionado]
                    endereco_completo = f"{bairro_selecionado} - {endereco_rua}" if bairro_selecionado != "Retirar no Local" else "Retirada no Local"
                    total_geral = total_itens + valor_frete
                    
                    pagamento_formatado = f"{pagamento} (Troco: R$ {troco})" if pagamento == "Dinheiro" and troco else pagamento
                    
                    salvar_cliente(telefone_limpo, nome_cliente, bairro_selecionado, endereco_rua)
                    pedido_id = salvar_novo_pedido(nome_cliente, telefone_limpo, endereco_completo, carrinho, total_geral, pagamento_formatado, valor_frete)

                    texto_pedido = f"Olá, Bem Caseiro! Gostaria de confirmar meu pedido #{pedido_id}:\n\n"
                    texto_pedido += f"👤 *Cliente:* {nome_cliente}\n"
                    texto_pedido += f"📱 *Contato:* {telefone_limpo}\n"
                    texto_pedido += f"📍 *Endereço:* {endereco_completo}\n\n"
                    texto_pedido += "*Itens do Pedido:*\n"
                    for item in carrinho:
                        texto_pedido += f"- {item['qtd']}x {item['nome']} (R$ {item['subtotal']:.2f})\n"
                    
                    texto_pedido += f"\n📦 *Subtotal:* R$ {total_itens:.2f}"
                    texto_pedido += f"\n🛵 *Taxa de Entrega:* R$ {valor_frete:.2f}"
                    texto_pedido += f"\n💰 *Total Geral:* R$ {total_geral:.2f}\n"
                    texto_pedido += f"💳 *Pagamento:* {pagamento_formatado}"

                    texto_codificado = urllib.parse.quote(texto_pedido)
                    link_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP}?text={texto_codificado}"

                    st.success(f"✅ Pedido #{pedido_id} registrado! Valor Total: R$ {total_geral:.2f}.")
                    st.markdown(
                        f'<a href="{link_whatsapp}" target="_blank" style="display: inline-block; padding: 10px 20px; background-color: #25D366; color: white; text-align: center; text-decoration: none; font-size: 16px; border-radius: 5px;">📱 Enviar Pedido por WhatsApp</a>',
                        unsafe_allow_html=True
                    )
                else:
                    st.error("Por favor, informe seu WhatsApp, Nome, adicione os itens e informe o endereço.")

# ==========================================
# 4. GESTÃO DO CARDÁPIO (COM EDIÇÃO)
# ==========================================
elif menu == "Gestão do Cardápio":
    st.title("📝 Gestão do Cardápio")

    with st.expander("➕ Cadastrar Novo Prato", expanded=False):
        with st.form("form_novo_prato", clear_on_submit=True):
            novo_nome = st.text_input("Nome do Prato/Bebida*")
            novo_preco = st.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=1.0)
            nova_imagem = st.text_input("Link da Imagem (Opcional)")
            
            if st.form_submit_button("Salvar no Cardápio"):
                if novo_nome and novo_preco > 0:
                    adicionar_prato(novo_nome, novo_preco, nova_imagem)
                    st.success(f"'{novo_nome}' adicionado!")
                    st.rerun()
                else:
                    st.error("Preencha nome e preço.")

    st.divider()
    st.subheader("Itens Cadastrados")
    
    cardapio_banco = carregar_cardapio_completo()
    
    if not cardapio_banco:
        st.info("Nenhum item cadastrado.")
    else:
        for item in cardapio_banco:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.write(f"**{item['nome']}**")
                c2.write(f"R$ {float(item['preco']):.2f}")
                
                is_ativo = bool(item['disponivel'])
                toggle_ativo = c3.toggle("Sim", value=is_ativo, key=f"tgl_{item['id']}")
                if toggle_ativo != is_ativo:
                    atualizar_disponibilidade(item['id'], int(toggle_ativo))
                    st.rerun()
                    
                if c4.button("🗑️ Excluir", key=f"del_{item['id']}"):
                    excluir_prato(item['id'])
                    st.rerun()
                
                with st.expander(f"✏️ Editar", expanded=False):
                    with st.form(f"form_edit_{item['id']}"):
                        edit_nome = st.text_input("Nome", value=item['nome'])
                        edit_preco = st.number_input("Preço (R$)", min_value=0.0, value=float(item['preco']), format="%.2f", step=1.0)
                        edit_imagem = st.text_input("Link da Imagem", value=item['imagem'] if item['imagem'] else "")
                        
                        if st.form_submit_button("Salvar Alterações"):
                            if edit_nome and edit_preco > 0:
                                editar_prato(item['id'], edit_nome, edit_preco, edit_imagem)
                                st.success("Atualizado!")
                                st.rerun()
            st.divider()

# ==========================================
# 5. MÓDULO DA COZINHA E FINANCEIRO (MANTIDOS)
# ==========================================
elif menu == "Painel da Cozinha / Gestão":
    st.title("📋 Painel de Controle de Pedidos")
    df_pedidos = carregar_pedidos_ativos()

    if df_pedidos.empty:
        st.info("A cozinha está limpa!")
    else:
        for index, row in df_pedidos.iterrows():
            with st.expander(f"Pedido #{row['id']} — {row['cliente']} — Status: [{row['status']}]", expanded=True):
                telefone_exibicao = row.get('telefone', '')
                st.markdown(f"**WhatsApp:** {telefone_exibicao} | **Pagamento:** {row['pagamento']}")
                st.markdown(f"**Endereço:** {row['endereco']}")
                
                itens = json.loads(row['itens'])
                for i in itens:
                    st.text(f"- {i['qtd']}x {i['nome']} (R$ {float(i['subtotal']):.2f})")
                
                taxa = float(row.get('taxa_entrega', 0.0))
                st.markdown(f"**Total (com R$ {taxa:.2f} frete): R$ {float(row['total']):.2f}**")

                col1, col2, col3, col4 = st.columns(4)
                if col1.button("Em Produção", key=f"prod_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Em Produção")
                    st.rerun()
                if col2.button("Saiu para Entrega", key=f"ent_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Saiu para Entrega")
                    st.rerun()
                if col3.button("✅ Concluir", key=f"conc_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Concluído")
                    st.rerun()
                if col4.button("❌ Cancelar", key=f"canc_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Cancelado")
                    st.rerun()

elif menu == "Relatório Financeiro":
    st.title("📊 Relatório Financeiro e Fechamento")
    df_vendas = carregar_vendas_concluidas()

    if df_vendas.empty:
        st.warning("Nenhuma venda concluída.")
    else:
        # Converter valores para float caso venham como formato genérico numérico do BD
        df_vendas['total'] = df_vendas['total'].astype(float)
        if 'taxa_entrega' in df_vendas.columns:
            df_vendas['taxa_entrega'] = df_vendas['taxa_entrega'].astype(float)
        else:
            df_vendas['taxa_entrega'] = 0.0
            
        faturamento_total = df_vendas['total'].sum()
        total_fretes = df_vendas['taxa_entrega'].sum()
        faturamento_produtos = faturamento_total - total_fretes
        qtd_pedidos = len(df_vendas)
        ticket_medio = faturamento_total / qtd_pedidos if qtd_pedidos > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Faturamento Bruto", f"R$ {faturamento_total:,.2f}")
        col2.metric("Só Produtos", f"R$ {faturamento_produtos:,.2f}")
        col3.metric("Total Fretes", f"R$ {total_fretes:,.2f}")
        col4.metric("Ticket Médio", f"R$ {ticket_medio:,.2f}")

        st.divider()
        st.subheader("Receita por Forma de Pagamento")
        receita_por_pagamento = df_vendas.groupby('pagamento')['total'].sum().reset_index()
        st.bar_chart(data=receita_por_pagamento.set_index('pagamento'))