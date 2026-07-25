import datetime
import urllib.parse
import sqlite3
import json
import pandas as pd
import streamlit as st
import re

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
# 1. FUNÇÕES DE BANCO DE DADOS (SQLite)
# ==========================================
def inicializar_banco():
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            cliente TEXT,
            endereco TEXT,
            itens TEXT,
            total REAL,
            pagamento TEXT,
            status TEXT
        )
    ''')
    
    c.execute("PRAGMA table_info(pedidos)")
    colunas_pedidos = [coluna[1] for coluna in c.fetchall()]
    if 'taxa_entrega' not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN taxa_entrega REAL DEFAULT 0.0")
    if 'telefone' not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN telefone TEXT DEFAULT ''")
        
    c.execute('''
        CREATE TABLE IF NOT EXISTS cardapio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            preco REAL,
            disponivel INTEGER,
            imagem TEXT
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM cardapio")
    if c.fetchone()[0] == 0:
        itens_iniciais = [
            ("Marmita Executiva Tradicional", 22.00, 1, "https://images.unsplash.com/photo-1628296939923-d64e9a6e35cb?w=300&q=80"),
            ("Prato Feito Especial", 28.00, 1, "https://images.unsplash.com/photo-1645696301019-35adcc18fc21?w=300&q=80"),
            ("Suco Natural 500ml", 8.00, 1, "https://images.unsplash.com/photo-1622597467836-f38240662c8b?w=300&q=80")
        ]
        c.executemany("INSERT INTO cardapio (nome, preco, disponivel, imagem) VALUES (?, ?, ?, ?)", itens_iniciais)

    conn.commit()
    conn.close()

def salvar_novo_pedido(cliente, telefone, endereco, itens, total, pagamento, taxa_entrega):
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    itens_json = json.dumps(itens)
    c.execute('''
        INSERT INTO pedidos (data_hora, cliente, telefone, endereco, itens, total, pagamento, status, taxa_entrega)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data_hora, cliente, telefone, endereco, itens_json, total, pagamento, 'Novo', taxa_entrega))
    pedido_id = c.lastrowid
    conn.commit()
    conn.close()
    return pedido_id

def carregar_pedidos_ativos():
    conn = sqlite3.connect('bem_caseiro.db')
    df = pd.read_sql_query("SELECT * FROM pedidos WHERE status NOT IN ('Concluído', 'Cancelado')", conn)
    conn.close()
    return df

def atualizar_status_pedido(pedido_id, novo_status):
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    c.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo_status, pedido_id))
    conn.commit()
    conn.close()

def carregar_vendas_concluidas():
    conn = sqlite3.connect('bem_caseiro.db')
    df = pd.read_sql_query("SELECT * FROM pedidos WHERE status = 'Concluído'", conn)
    conn.close()
    return df

def carregar_cardapio_completo():
    conn = sqlite3.connect('bem_caseiro.db')
    df = pd.read_sql_query("SELECT * FROM cardapio", conn)
    conn.close()
    return df.to_dict('records')

def adicionar_prato(nome, preco, imagem):
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    c.execute("INSERT INTO cardapio (nome, preco, disponivel, imagem) VALUES (?, ?, 1, ?)", (nome, preco, imagem))
    conn.commit()
    conn.close()

def atualizar_disponibilidade(prato_id, disponivel):
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    c.execute("UPDATE cardapio SET disponivel = ? WHERE id = ?", (disponivel, prato_id))
    conn.commit()
    conn.close()

def excluir_prato(prato_id):
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    c.execute("DELETE FROM cardapio WHERE id = ?", (prato_id,))
    conn.commit()
    conn.close()

# --- NOVA FUNÇÃO PARA EDITAR O PRATO ---
def editar_prato(prato_id, nome, preco, imagem):
    conn = sqlite3.connect('bem_caseiro.db')
    c = conn.cursor()
    c.execute("UPDATE cardapio SET nome = ?, preco = ?, imagem = ? WHERE id = ?", (nome, preco, imagem, prato_id))
    conn.commit()
    conn.close()

inicializar_banco()

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
                    st.markdown(f"R$ {item['preco']:.2f}")
                with col_qtd:
                    qtd = st.number_input("Quantidade", min_value=0, max_value=20, value=0, key=f"item_cli_{item['id']}")
                    if qtd > 0:
                        subtotal = qtd * item["preco"]
                        carrinho.append({"nome": item["nome"], "qtd": qtd, "subtotal": subtotal})
                        total_itens += subtotal
            st.divider()

        st.markdown(f"### Subtotal dos itens: R$ {total_itens:.2f}")
        st.divider()

        st.subheader("Dados para Entrega")
        
        col_nome, col_tel = st.columns(2)
        with col_nome:
            nome_cliente = st.text_input("Nome Completo")
        with col_tel:
            telefone_cliente = st.text_input("WhatsApp para Contato (Ex: 95 99999-9999)")
        
        col_bairro, col_rua = st.columns([1, 2])
        with col_bairro:
            bairro_selecionado = st.selectbox("Bairro", list(TAXAS_ENTREGA.keys()))
            valor_frete = TAXAS_ENTREGA[bairro_selecionado]
        with col_rua:
            endereco_rua = st.text_input("Rua, Número e Ponto de Referência")

        endereco_completo = f"{bairro_selecionado} - {endereco_rua}" if bairro_selecionado != "Retirar no Local" else "Retirada no Local"
        total_geral = total_itens + valor_frete

        st.info(f"**Taxa de Entrega:** R$ {valor_frete:.2f} | **Total do Pedido:** R$ {total_geral:.2f}")

        pagamento = st.selectbox("Forma de Pagamento", ["Pix", "Cartão (Entrega)", "Dinheiro"])
        troco = st.text_input("Troco para quanto? (Se for dinheiro)")

        st.write("") 
        enviar = st.button("Finalizar e Enviar para o WhatsApp", type="primary", use_container_width=True)

        if enviar:
            if nome_cliente and telefone_cliente and carrinho and (endereco_rua or bairro_selecionado == "Retirar no Local"):
                pagamento_formatado = f"{pagamento} (Troco: R$ {troco})" if pagamento == "Dinheiro" and troco else pagamento
                
                pedido_id = salvar_novo_pedido(nome_cliente, telefone_cliente, endereco_completo, carrinho, total_geral, pagamento_formatado, valor_frete)

                texto_pedido = f"Olá, Bem Caseiro! Gostaria de confirmar meu pedido #{pedido_id}:\n\n"
                texto_pedido += f"👤 *Cliente:* {nome_cliente}\n"
                texto_pedido += f"📱 *Contato:* {telefone_cliente}\n"
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
                st.error("Por favor, preencha o nome, telefone, adicione os itens e informe o endereço completo.")

# ==========================================
# 4. GESTÃO DO CARDÁPIO (COM EDIÇÃO)
# ==========================================
elif menu == "Gestão do Cardápio":
    st.title("📝 Gestão do Cardápio")
    st.write("Adicione novos pratos, ajuste preços ou marque um item como esgotado.")

    with st.expander("➕ Cadastrar Novo Prato", expanded=False):
        with st.form("form_novo_prato", clear_on_submit=True):
            novo_nome = st.text_input("Nome do Prato/Bebida*")
            novo_preco = st.number_input("Preço (R$)*", min_value=0.0, format="%.2f", step=1.0)
            nova_imagem = st.text_input("Link da Imagem (Opcional)")
            
            submit_prato = st.form_submit_button("Salvar no Cardápio")
            if submit_prato:
                if novo_nome and novo_preco > 0:
                    adicionar_prato(novo_nome, novo_preco, nova_imagem)
                    st.success(f"'{novo_nome}' adicionado com sucesso!")
                    st.rerun()
                else:
                    st.error("Por favor, preencha o nome e o preço corretamente.")

    st.divider()
    st.subheader("Itens Cadastrados")
    
    cardapio_banco = carregar_cardapio_completo()
    
    if not cardapio_banco:
        st.info("Nenhum item cadastrado no cardápio.")
    else:
        col_nome, col_preco, col_disp, col_acao = st.columns([3, 1, 1, 1])
        col_nome.markdown("**Produto**")
        col_preco.markdown("**Preço**")
        col_disp.markdown("**Disponível?**")
        col_acao.markdown("**Ações**")
        
        for item in cardapio_banco:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.write(f"**{item['nome']}**")
                c2.write(f"R$ {item['preco']:.2f}")
                
                is_ativo = bool(item['disponivel'])
                toggle_ativo = c3.toggle("Sim", value=is_ativo, key=f"tgl_{item['id']}")
                if toggle_ativo != is_ativo:
                    atualizar_disponibilidade(item['id'], int(toggle_ativo))
                    st.rerun()
                    
                if c4.button("🗑️ Excluir", key=f"del_{item['id']}"):
                    excluir_prato(item['id'])
                    st.rerun()
                
                # --- ABA DE EDIÇÃO QUE SE EXPANDE ABAIXO DO ITEM ---
                with st.expander(f"✏️ Editar: {item['nome']}", expanded=False):
                    with st.form(f"form_edit_{item['id']}"):
                        edit_nome = st.text_input("Nome", value=item['nome'])
                        edit_preco = st.number_input("Preço (R$)", min_value=0.0, value=float(item['preco']), format="%.2f", step=1.0)
                        edit_imagem = st.text_input("Link da Imagem", value=item['imagem'] if item['imagem'] else "")
                        
                        salvar_edicao = st.form_submit_button("Salvar Alterações")
                        if salvar_edicao:
                            if edit_nome and edit_preco > 0:
                                editar_prato(item['id'], edit_nome, edit_preco, edit_imagem)
                                st.success("Prato atualizado com sucesso!")
                                st.rerun()
                            else:
                                st.error("O nome e o preço não podem ficar vazios.")
            st.divider()

# ==========================================
# 5. MÓDULO DA COZINHA (GESTÃO DE FILA)
# ==========================================
elif menu == "Painel da Cozinha / Gestão":
    st.title("📋 Painel de Controle de Pedidos")

    df_pedidos = carregar_pedidos_ativos()

    if df_pedidos.empty:
        st.info("Nenhum pedido ativo no momento. A cozinha está limpa!")
    else:
        for index, row in df_pedidos.iterrows():
            with st.expander(
                f"Pedido #{row['id']} — {row['cliente']} ({row['data_hora']}) — Status: [{row['status']}]",
                expanded=True,
            ):
                telefone_exibicao = row.get('telefone', 'Não informado')
                st.markdown(f"**WhatsApp:** {telefone_exibicao}")
                st.markdown(f"**Endereço:** {row['endereco']}")
                st.markdown(f"**Pagamento:** {row['pagamento']}")
                
                itens = json.loads(row['itens'])
                st.markdown("**Itens do Pedido:**")
                for i in itens:
                    st.text(f"- {i['qtd']}x {i['nome']} (R$ {i['subtotal']:.2f})")
                
                taxa = row.get('taxa_entrega', 0.0)
                st.markdown(f"**Taxa de Entrega:** R$ {taxa:.2f}")
                st.markdown(f"**Total a Cobrar:** R$ {row['total']:.2f}")

                st.divider()
                
                telefone_limpo = re.sub(r'\D', '', telefone_exibicao)
                if len(telefone_limpo) >= 10:
                    if not telefone_limpo.startswith('55'):
                        telefone_limpo = f"55{telefone_limpo}"
                    
                    msg_confirmacao = urllib.parse.quote(f"Olá {row['cliente']}! Vimos que você iniciou o pedido #{row['id']} no Bem Caseiro. Deseja confirmar para começarmos o preparo? 🍲")
                    msg_producao = urllib.parse.quote(f"Olá {row['cliente']}! Seu pedido #{row['id']} já está na nossa cozinha sendo preparado com todo carinho! 👨‍🍳")
                    msg_entrega = urllib.parse.quote(f"Boas notícias, {row['cliente']}! Seu pedido #{row['id']} acabou de sair para entrega. O entregador está a caminho! 🛵💨")

                    st.markdown("**📱 Avisar Cliente (Abre o WhatsApp Web):**")
                    st.markdown(f"""
                        <a href="https://wa.me/{telefone_limpo}?text={msg_confirmacao}" target="_blank" style="font-size: 14px; text-decoration: none; padding: 5px 10px; background-color: #f0f2f6; color: black; border-radius: 5px; margin-right: 5px;">❔ Perguntar se Confirma</a>
                        <a href="https://wa.me/{telefone_limpo}?text={msg_producao}" target="_blank" style="font-size: 14px; text-decoration: none; padding: 5px 10px; background-color: #ff9800; color: white; border-radius: 5px; margin-right: 5px;">🔥 Avisar: Em Produção</a>
                        <a href="https://wa.me/{telefone_limpo}?text={msg_entrega}" target="_blank" style="font-size: 14px; text-decoration: none; padding: 5px 10px; background-color: #4CAF50; color: white; border-radius: 5px;">🛵 Avisar: Saiu para Entrega</a>
                    """, unsafe_allow_html=True)
                    st.write("") 
                
                st.markdown("**Ações do Pedido (Sistema):**")
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

# ==========================================
# 6. MÓDULO FINANCEIRO (RELATÓRIOS)
# ==========================================
elif menu == "Relatório Financeiro":
    st.title("📊 Relatório Financeiro e Fechamento")

    df_vendas = carregar_vendas_concluidas()

    if df_vendas.empty:
        st.warning("Nenhuma venda concluída foi registrada ainda.")
    else:
        df_vendas['data_hora'] = pd.to_datetime(df_vendas['data_hora'], format="%d/%m/%Y %H:%M:%S")

        st.subheader("Resumo Geral das Vendas")
        
        faturamento_total = df_vendas['total'].sum()
        total_fretes = df_vendas['taxa_entrega'].sum() if 'taxa_entrega' in df_vendas.columns else 0.0
        faturamento_produtos = faturamento_total - total_fretes
        
        qtd_pedidos = len(df_vendas)
        ticket_medio = faturamento_total / qtd_pedidos if qtd_pedidos > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Faturamento Bruto", f"R$ {faturamento_total:,.2f}")
        col2.metric("Receita (Só Produtos)", f"R$ {faturamento_produtos:,.2f}")
        col3.metric("Total em Fretes", f"R$ {total_fretes:,.2f}")
        col4.metric("Ticket Médio", f"R$ {ticket_medio:,.2f}")

        st.divider()

        st.subheader("Receita por Forma de Pagamento")
        receita_por_pagamento = df_vendas.groupby('pagamento')['total'].sum().reset_index()
        
        col_grafico, col_tabela = st.columns([2, 1])
        with col_grafico:
            st.bar_chart(data=receita_por_pagamento.set_index('pagamento'))
        with col_tabela:
            st.dataframe(
                receita_por_pagamento.rename(columns={'pagamento': 'Pagamento', 'total': 'Total (R$)'}),
                hide_index=True,
                use_container_width=True
            )