import streamlit as st
import sqlite3
import json
import os
from datetime import datetime, date, timedelta
from google import genai
from google.genai import types

# ----------------------------------------------------
# 1. CONFIGURAÇÃO DA API GEMINI
# ----------------------------------------------------
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

client = genai.Client(api_key=GEMINI_API_KEY)

# ----------------------------------------------------
# 2. BANCO DE DADOS (COM COLUNA CARGO)
# ----------------------------------------------------
conn = sqlite3.connect("historico_estudos.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS questoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT,
    concurso TEXT,
    cargo TEXT,
    banca TEXT,
    materia TEXT,
    enunciado TEXT,
    gabarito TEXT,
    resposta_usuario TEXT,
    acertou INTEGER
)
""")

# Garante compatibilidade caso a coluna cargo ainda não exista
try:
    cursor.execute("ALTER TABLE questoes ADD COLUMN cargo TEXT")
except:
    pass
conn.commit()

# ----------------------------------------------------
# 3. MAPEAMENTO DOS 3 CARGOS
# ----------------------------------------------------
CARGOS_INFO = {
    "Dataprev - Analista de TI": {
        "concurso": "Dataprev",
        "banca": "FGV",
        "materias": "Banco de Dados, Governança de TI (COBIT/ITIL), Engenharia de Software, Segurança da Informação, Raciocínio Lógico e Português (FGV)."
    },
    "Transpetro - Analista SAP": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": "Módulos SAP (ECC/S4HANA, MM, PM, FI, CO, ABAP), Integração de Sistemas, Governança de TI, Raciocínio Lógico e Português (Cesgranrio)."
    },
    "Transpetro - Mecânico de Manutenção": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": "Mecânica dos Fluidos, Bombas e Compressores, Manutenção Preditiva/Preventiva, Soldagem, Ensaios Não Destrutivos, Metrologia, Elementos de Máquinas, Desenho Técnico, Raciocínio Lógico e Português."
    }
}

# ----------------------------------------------------
# 4. GERADOR DE QUESTÕES
# ----------------------------------------------------
def gerar_questao(cargo_selecionado):
    if cargo_selecionado == "Ciclo Automático (Todos os Cargos)":
        cursor.execute("""
            SELECT cargo, materia, AVG(CASE WHEN acertou = 1 THEN 1.0 ELSE 0.0 END) as taxa 
            FROM questoes 
            WHERE resposta_usuario != 'NÃO SEI' AND cargo IS NOT NULL
            GROUP BY cargo, materia 
            ORDER BY taxa ASC 
            LIMIT 1
        """)
        pior = cursor.fetchone()
        if pior:
            cargo_alvo = pior[0] if pior[0] in CARGOS_INFO else "Dataprev - Analista de TI"
            contexto_fraqueza = f"Foco de fraqueza detectado no cargo {cargo_alvo} na matéria {pior[1]}"
        else:
            cargo_alvo = "Dataprev - Analista de TI"
            contexto_fraqueza = "Início do ciclo adaptativo"
    else:
        cargo_alvo = cargo_selecionado
        cursor.execute("""
            SELECT materia, AVG(CASE WHEN acertou = 1 THEN 1.0 ELSE 0.0 END) as taxa 
            FROM questoes 
            WHERE resposta_usuario != 'NÃO SEI' AND cargo = ?
            GROUP BY materia 
            ORDER BY taxa ASC 
            LIMIT 1
        """, (cargo_alvo,))
        pior = cursor.fetchone()
        contexto_fraqueza = f"Foco de fraqueza no cargo {cargo_alvo}: {pior[0]}" if pior else f"Início de treino para {cargo_alvo}"

    info = CARGOS_INFO[cargo_alvo]

    prompt_instrucao = f"""
    Atue como Diretor Especialista em Concursos Públicos.
    Concurso: {info['concurso']}
    Cargo: {cargo_alvo}
    Banca Examinadora: {info['banca']}
    Ementa do Cargo: {info['materias']}
    Status do Aluno: {contexto_fraqueza}

    Gere UMA questão inédita com alto rigor técnico da banca correspondente.
    Retorne ESTRITAMENTE em formato JSON com o seguinte schema:
    {{
        "concurso": "{info['concurso']}",
        "cargo": "{cargo_alvo}",
        "banca": "{info['banca']}",
        "materia": "Nome da Matéria",
        "assunto": "Tópico Específico",
        "enunciado": "Texto da questão claro e objetivo",
        "opcoes": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
        "gabarito": "A, B, C, D ou E",
        "explicacao_rapida": "Resumo do porquê o gabarito está certo."
    }}
    """
    
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt_instrucao,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

# ----------------------------------------------------
# 5. GERADOR DE AULA COMPLETA
# ----------------------------------------------------
def gerar_aula_profunda(q):
    prompt_aula = f"""
    Você é um professor titular renomado preparando um candidato para a banca {q['banca']} no cargo {q.get('cargo', q['concurso'])}.
    O aluno marcou 'Não Sei' no assunto:
    - Matéria: {q['materia']}
    - Assunto: {q.get('assunto', '')}
    - Enunciado: {q['enunciado']}
    - Alternativas: {json.dumps(q['opcoes'], ensure_ascii=False)}
    - Gabarito Oficial: {q['gabarito']}

    Escreva uma AULA TEÓRICA E PRÁTICA COMPLETA em Markdown com as seguintes seções:
    ## 🏛️ 1. Fundamentação Teórica Completa
    Explique o conceito fundamental do zero com rigor técnico, fórmulas/normas se aplicável e contexto prático do cargo.
    
    ## 🔍 2. Análise Detalhada Alternativa por Alternativa
    Explique por que a alternativa {q['gabarito']} é a correta e aponte o erro de cada uma das outras alternativas.
    
    ## ⚡ 3. O Padrão da Banca ({q['banca']}) & Pegadinhas
    Como a banca cobra esse assunto e qual a armadilha clássica.
    
    ## 🧠 4. Resumo Prático & Mnemônico / Regra de Ouro
    Tópicos rápidos ou mnemônico para acertar em 30 segundos na prova.
    """

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt_aula
    )
    return response.text

# ----------------------------------------------------
# 6. ESTRUTURA DO APP & NAVEGAÇÃO
# ----------------------------------------------------
st.set_page_config(page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide")

st.sidebar.title("📚 Central de Estudos")
menu = st.sidebar.radio("Navegar:", ["📝 Treino de Questões", "📊 Dashboard Geral & Por Cargo"])

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Foco de Estudo Atual:")
cargo_selecionado = st.sidebar.selectbox(
    "Escolha o Cargo:",
    ["Ciclo Automático (Todos os Cargos)"] + list(CARGOS_INFO.keys())
)

# ====================================================
# TELA 1: ÁREA DE QUESTÕES
# ====================================================
if menu == "📝 Treino de Questões":
    st.title("🎯 Treino de Questões Adaptativo")
    
    # Reinicia a questão caso troque de cargo manualmente
    if "cargo_atual_memoria" not in st.session_state or st.session_state.cargo_atual_memoria != cargo_selecionado:
        st.session_state.cargo_atual_memoria = cargo_selecionado
        st.session_state.questao_atual = None

    if st.session_state.get("questao_atual") is None:
        with st.spinner(f"Gerando questão inédita para: {cargo_selecionado}..."):
            st.session_state.questao_atual = gerar_questao(cargo_selecionado)
            st.session_state.status_resposta = None
            st.session_state.escolha = None
            st.session_state.aula_gerada = None

    q = st.session_state.questao_atual

    st.info(f"📌 **Cargo:** {q.get('cargo', q['concurso'])} | **Banca:** {q['banca']} | **Matéria:** {q['materia']} — *{q.get('assunto', '')}*")
    st.markdown(f"### {q['enunciado']}")

    opcoes = q["opcoes"]
    disabled = st.session_state.status_resposta is not None

    escolha = st.radio(
        "Selecione sua alternativa:", 
        list(opcoes.keys()), 
        format_func=lambda x: f"{x}) {opcoes[x]}",
        disabled=disabled,
        key="radio_opcao"
    )

    col1, col2 = st.columns([1, 1])

    if not disabled:
        with col1:
            if st.button("✅ Confirmar Resposta", type="primary", use_container_width=True):
                st.session_state.escolha = escolha
                acertou = 1 if escolha == q["gabarito"] else 0
                st.session_state.status_resposta = "acertou" if acertou == 1 else "errou"
                
                cursor.execute(
                    "INSERT INTO questoes (data, concurso, cargo, banca, materia, enunciado, gabarito, resposta_usuario, acertou) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), q["concurso"], q.get("cargo", cargo_selecionado), q["banca"], q["materia"], q["enunciado"], q["gabarito"], escolha, acertou)
                )
                conn.commit()
                st.rerun()

        with col2:
            if st.button("🤷 Não sei o assunto (Abrir Aula Completa)", type="secondary", use_container_width=True):
                st.session_state.escolha = "NÃO SEI"
                st.session_state.status_resposta = "nao_sei"
                
                cursor.execute(
                    "INSERT INTO questoes (data, concurso, cargo, banca, materia, enunciado, gabarito, resposta_usuario, acertou) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), q["concurso"], q.get("cargo", cargo_selecionado), q["banca"], q["materia"], q["enunciado"], q["gabarito"], "NÃO SEI", 0)
                )
                conn.commit()
                st.rerun()

    if disabled:
        st.markdown("---")
        if st.session_state.status_resposta == "acertou":
            st.success(f"🎉 **ACERTOU!** O gabarito oficial é **{q['gabarito']}**.")
            st.write(q["explicacao_rapida"])
        elif st.session_state.status_resposta == "errou":
            st.error(f"❌ **ERROU!** Você marcou **{st.session_state.escolha}**, mas o gabarito oficial é **{q['gabarito']}**.")
            st.write(q["explicacao_rapida"])
        elif st.session_state.status_resposta == "nao_sei":
            st.warning(f"💡 **Modo Aula Teórica Profunda Ativado!** Gabarito oficial: **{q['gabarito']}**.")
            
            if st.session_state.aula_gerada is None:
                with st.spinner("Construindo aula completa com fundamentação teórica e padrão de banca..."):
                    st.session_state.aula_gerada = gerar_aula_profunda(q)
            
            st.markdown(st.session_state.aula_gerada)

        st.markdown("---")
        if st.button("Próxima Questão ➡️", type="primary", use_container_width=True):
            with st.spinner("Buscando próxima questão..."):
                st.session_state.questao_atual = gerar_questao(cargo_selecionado)
                st.session_state.status_resposta = None
                st.session_state.escolha = None
                st.session_state.aula_gerada = None
                st.rerun()

# ====================================================
# TELA 2: DASHBOARD GERAL E POR CARGO
# ====================================================
elif menu == "📊 Dashboard Geral & Por Cargo":
    st.title("📊 Painel de Desempenho & Panorama dos 3 Concursos")
    
    hoje_str = date.today().strftime("%Y-%m-%d")
    inicio_semana = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    inicio_mes = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Volume Geral
    tot_h = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ?", (hoje_str,)).fetchone()[0]
    tot_s = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ?", (inicio_semana,)).fetchone()[0]
    tot_m = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ?", (inicio_mes,)).fetchone()[0]
    tot_g = cursor.execute("SELECT COUNT(*) FROM questoes").fetchone()[0]

    ac_h = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ? AND acertou = 1", (hoje_str,)).fetchone()[0]
    ac_s = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ? AND acertou = 1", (inicio_semana,)).fetchone()[0]
    ac_m = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ? AND acertou = 1", (inicio_mes,)).fetchone()[0]
    ac_g = cursor.execute("SELECT COUNT(*) FROM questoes WHERE acertou = 1").fetchone()[0]

    st.subheader("📅 Volume Global de Treino")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hoje", f"{tot_h} questões", f"{(ac_h/tot_h*100) if tot_h>0 else 0:.1f}% acerto")
    c2.metric("Últimos 7 Dias", f"{tot_s} questões", f"{(ac_s/tot_s*100) if tot_s>0 else 0:.1f}% acerto")
    c3.metric("Últimos 30 Dias", f"{tot_m} questões", f"{(ac_m/tot_m*100) if tot_m>0 else 0:.1f}% acerto")
    c4.metric("Total Geral", f"{tot_g} questões", f"{(ac_g/tot_g*100) if tot_g>0 else 0:.1f}% acerto")

    st.markdown("---")
    st.subheader("🎯 Panorama Individual por Concurso / Cargo")

    tab_dataprev, tab_sap, tab_mecanico = st.tabs([
        "🏢 Dataprev (Analista TI)", 
        "🛢️ Transpetro (Analista SAP)", 
        "⚙️ Transpetro (Mecânico Manutenção)"
    ])

    def renderizar_painel_cargo(nome_cargo, meta_questoes=300):
        tot = cursor.execute("SELECT COUNT(*) FROM questoes WHERE cargo = ? OR concurso = ?", (nome_cargo, nome_cargo.split(' - ')[0])).fetchone()[0]
        ac = cursor.execute("SELECT COUNT(*) FROM questoes WHERE (cargo = ? OR concurso = ?) AND acertou = 1", (nome_cargo, nome_cargo.split(' - ')[0])).fetchone()[0]
        duv = cursor.execute("SELECT COUNT(*) FROM questoes WHERE (cargo = ? OR concurso = ?) AND resposta_usuario = 'NÃO SEI'", (nome_cargo, nome_cargo.split(' - ')[0])).fetchone()[0]

        taxa = (ac / tot * 100) if tot > 0 else 0
        restantes = max(meta_questoes - tot, 0)
        progresso = min(tot / meta_questoes, 1.0)

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Questões Resolvidas", f"{tot} questões")
        col_m2.metric("Acertos", f"{ac} questões")
        col_m3.metric("Aulas Solicitadas", f"{duv}")
        col_m4.metric("Aproveitamento", f"{taxa:.1f}%")

        st.write(f"**Termômetro de Prontidão (Meta: {meta_questoes} questões resolvidas):**")
        st.progress(progresso)
        
        c_status1, c_status2 = st.columns(2)
        with c_status1:
            st.info(f"📌 **Faltam {restantes} questões** para a base competitiva deste cargo.")
        with c_status2:
            if taxa >= 80 and tot >= 150:
                st.success("🟢 **Status:** Nível Competitivo de Alta Performance!")
            elif taxa >= 60:
                st.warning("🟡 **Status:** Nível Intermediário — Em evolução.")
            else:
                st.error("🔴 **Status:** Fase de Construção de Base.")

        st.markdown("#### 📊 Diagnóstico por Matéria:")
        stats_mat = cursor.execute("""
            SELECT materia, COUNT(*), SUM(CASE WHEN acertou = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN resposta_usuario = 'NÃO SEI' THEN 1 ELSE 0 END)
            FROM questoes
            WHERE cargo = ? OR concurso = ?
            GROUP BY materia
            ORDER BY (CAST(SUM(CASE WHEN acertou = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) ASC
        """, (nome_cargo, nome_cargo.split(' - ')[0])).fetchall()

        if stats_mat:
            tabela = []
            for mat, t, a, d in stats_mat:
                acertos_mat = a or 0
                tx = (acertos_mat / t) * 100
                status_txt = "🔴 Prioridade Alta" if tx < 60 else ("🟡 Atenção" if tx < 80 else "🟢 Dominado")
                tabela.append({
                    "Matéria": mat,
                    "Total de Questões": t,
                    "Acertos": acertos_mat,
                    "Aulas Solicitadas": d,
                    "Aproveitamento": f"{tx:.1f}%",
                    "Diagnóstico": status_txt
                })
            st.table(tabela)
        else:
            st.caption("Nenhuma questão resolvida para este cargo ainda.")

    with tab_dataprev:
        renderizar_painel_cargo("Dataprev - Analista de TI", meta_questoes=400)

    with tab_sap:
        renderizar_painel_cargo("Transpetro - Analista SAP", meta_questoes=350)

    with tab_mecanico:
        renderizar_painel_cargo("Transpetro - Mecânico de Manutenção", meta_questoes=350)
