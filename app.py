import datetime
import urllib.parse
import sqlite3
import json
import pandas as pd
import streamlit as st

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
    
    # Atualiza o banco adicionando as colunas novas sem perder dados antigos
    c.execute("PRAGMA table_info(pedidos)")
    colunas = [coluna[1] for coluna in c.fetchall()]
    
    if 'taxa_entrega' not in colunas:
        c.execute("ALTER TABLE pedidos ADD COLUMN taxa_entrega REAL DEFAULT 0.0")
    if 'telefone' not in colunas:
        c.execute("ALTER TABLE pedidos ADD COLUMN telefone TEXT DEFAULT ''")
        
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
    df = pd.read_sql_query("SELECT * FROM pedidos WHERE status != 'Concluído'", conn)
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

inicializar_banco()

# ==========================================
# 2. CONFIGURAÇÃO DA INTERFACE (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Bem Caseiro Delivery", page_icon="🍲", layout="wide")

if "cardapio" not in st.session_state:
    st.session_state.cardapio = [
        {"id": 1, "nome": "Marmita Executiva Tradicional", "preco": 22.00, "disponivel": True, "imagem": "https://images.unsplash.com/photo-1628296939923-d64e9a6e35cb?w=300&q=80"},
        {"id": 2, "nome": "Prato Feito Especial", "preco": 28.00, "disponivel": True, "imagem": "https://images.unsplash.com/photo-1645696301019-35adcc18fc21?w=300&q=80"},
        {"id": 3, "nome": "Suco Natural 500ml", "preco": 8.00, "disponivel": True, "imagem": "https://images.unsplash.com/photo-1622597467836-f38240662c8b?w=300&q=80"},
    ]

menu = st.sidebar.selectbox(
    "Navegação", 
    ["Fazer Pedido (Cliente)", "Painel da Cozinha / Gestão", "Relatório Financeiro"]
)

# ==========================================
# 3. MÓDULO DO CLIENTE (CARDÁPIO)
# ==========================================
if menu == "Fazer Pedido (Cliente)":
    st.title("🍽️ Bem Caseiro - Faça o seu Pedido")
    st.subheader("Nosso Cardápio:")

    carrinho = []
    total_itens = 0.0

    for item in st.session_state.cardapio:
        if item["disponivel"]:
            with st.container():
                col_img, col_desc, col_qtd = st.columns([1, 3, 1])
                with col_img:
                    if item.get("imagem"):
                        st.image(item["imagem"], use_container_width=True)
                with col_desc:
                    st.markdown(f"**{item['nome']}**")
                    st.markdown(f"R$ {item['preco']:.2f}")
                with col_qtd:
                    qtd = st.number_input("Quantidade", min_value=0, max_value=20, value=0, key=f"item_{item['id']}")
                    if qtd > 0:
                        subtotal = qtd * item["preco"]
                        carrinho.append({"nome": item["nome"], "qtd": qtd, "subtotal": subtotal})
                        total_itens += subtotal
            st.divider()

    st.markdown(f"### Subtotal dos itens: R$ {total_itens:.2f}")

    with st.form("form_cliente"):
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

        enviar = st.form_submit_button("Finalizar e Enviar para o WhatsApp")

        if enviar:
            if nome_cliente and telefone_cliente and carrinho and (endereco_rua or bairro_selecionado == "Retirar no Local"):
                pagamento_formatado = f"{pagamento} (Troco: R$ {troco})" if pagamento == "Dinheiro" and troco else pagamento
                
                # Salvando no banco com o novo campo de telefone
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

                st.success(f"✅ Pedido #{pedido_id} registrado! Valor Total: R$ {total_geral:.2f}. Clique abaixo para nos enviar no WhatsApp.")
                st.markdown(
                    f'<a href="{link_whatsapp}" target="_blank" style="display: inline-block; padding: 10px 20px; background-color: #25D366; color: white; text-align: center; text-decoration: none; font-size: 16px; border-radius: 5px;">📱 Enviar Pedido por WhatsApp</a>',
                    unsafe_allow_html=True
                )
            else:
                st.error("Por favor, preencha o nome, telefone, adicione os itens e informe o endereço completo.")

# ==========================================
# 4. MÓDULO DA COZINHA (GESTÃO DE FILA)
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

                col1, col2, col3 = st.columns(3)
                if col1.button("Em Produção", key=f"prod_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Em Produção")
                    st.rerun()
                if col2.button("Saiu para Entrega", key=f"ent_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Saiu para Entrega")
                    st.rerun()
                if col3.button("Concluir (Arquivar)", key=f"conc_{row['id']}"):
                    atualizar_status_pedido(row['id'], "Concluído")
                    st.rerun()

# ==========================================
# 5. MÓDULO FINANCEIRO (RELATÓRIOS)
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