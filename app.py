import streamlit as st
import sqlite3
import json
import os
from datetime import datetime, date, timedelta
from google import genai
from google.genai import types

# ----------------------------------------------------
# 1. CONFIGURAÇÃO SEGURA DA API GEMINI
# ----------------------------------------------------
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

client = genai.Client(api_key=GEMINI_API_KEY)

# ----------------------------------------------------
# 2. BANCO DE DADOS LOCAL (SQLITE)
# ----------------------------------------------------
conn = sqlite3.connect("historico_estudos.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS questoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT,
    concurso TEXT,
    banca TEXT,
    materia TEXT,
    enunciado TEXT,
    gabarito TEXT,
    resposta_usuario TEXT,
    acertou INTEGER
)
""")
conn.commit()

# ----------------------------------------------------
# 3. FUNÇÃO PARA GERAR QUESTÕES
# ----------------------------------------------------
def gerar_questao():
    cursor.execute("""
        SELECT materia, AVG(CASE WHEN acertou = 1 THEN 1.0 ELSE 0.0 END) as taxa 
        FROM questoes 
        WHERE resposta_usuario != 'NÃO SEI'
        GROUP BY materia 
        ORDER BY taxa ASC 
        LIMIT 1
    """)
    pior_desempenho = cursor.fetchone()
    contexto_fraqueza = f"Foco prioritário na fraqueza do aluno: {pior_desempenho[0]}" if pior_desempenho else "Início do ciclo adaptativo"

    prompt_instrucao = f"""
    Atue como Diretor Virtual de Estudos Especialista em Concursos Públicos.
    Concursos-alvo:
    1. Dataprev (FGV) - Informática, Governança, Lógica, Português.
    2. Transpetro (Cesgranrio) - Conhecimentos Específicos e Gerais.
    
    Perfil do Aluno: Foco em clareza, termos-chave em negrito, alta retenção.
    Status atual: {contexto_fraqueza}.

    Gere UMA questão inédita no estilo autêntico da banca correspondente.
    Retorne ESTRITAMENTE em formato JSON com o seguinte schema:
    {{
        "concurso": "Dataprev ou Transpetro",
        "banca": "FGV ou Cesgranrio",
        "materia": "Nome da Matéria",
        "assunto": "Tópico Específico",
        "enunciado": "Texto claro e bem estruturado da questão",
        "opcoes": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
        "gabarito": "A, B, C, D ou E",
        "explicacao_rapida": "Resumo objetivo do porquê o gabarito está certo."
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
# 4. FUNÇÃO DEDICADA: AULA COMPLETA E APROFUNDADA
# ----------------------------------------------------
def gerar_aula_profunda(q):
    prompt_aula = f"""
    Você é um professor titular renomado preparando um candidato de elite para a banca {q['banca']} no concurso {q['concurso']}.
    O aluno marcou 'Não Sei' para o seguinte conteúdo:
    - Matéria: {q['materia']}
    - Assunto: {q.get('assunto', '')}
    - Enunciado da questão: {q['enunciado']}
    - Alternativas: {json.dumps(q['opcoes'], ensure_ascii=False)}
    - Gabarito Oficial: {q['gabarito']}

    Escreva uma AULA TEÓRICA E PRÁTICA COMPLETA, profunda, densa e didática em Markdown, dividida exatamente nas seguintes seções:

    ## 🏛️ 1. Fundamentação Teórica Completa
    Explique o conceito fundamental do zero com rigor técnico, definições formais, leis/regras/normas aplicáveis e contexto prático de TI/Concurso. Não economize na explicação.

    ## 🔍 2. Análise Detalhada Alternativa por Alternativa
    Explique detalhadamente por que a alternativa correta ({q['gabarito']}) é a certa e destrinche exatamente o erro de cada uma das outras alternativas incorretas.

    ## ⚡ 3. O Padrão da Banca ({q['banca']}) & Pegadinhas
    Como a banca costuma cobrar esse assunto? Qual é a armadilha típica que faz o candidato médio errar essa questão?

    ## 🧠 4. Resumo Prático & Mnemônico / Regra de Ouro
    Um esquema visual resumido em tópicos, tabela ou mnemônico para bater o olho na hora da prova e acertar em 30 segundos.
    """

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt_aula
    )
    return response.text

# ----------------------------------------------------
# 5. ESTRUTURA DO APP & MENU LATERAL
# ----------------------------------------------------
st.set_page_config(page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide")

st.sidebar.title("📚 Menu de Navegação")
menu = st.sidebar.radio("Ir para:", ["📝 Treino de Questões", "📊 Dashboard Completo"])

# ====================================================
# TELA 1: TREINO ADAPTATIVO
# ====================================================
if menu == "📝 Treino de Questões":
    st.title("🎯 Treino de Questões Adaptativo")
    
    if "questao_atual" not in st.session_state:
        with st.spinner("Gerando questão inédita sob medida..."):
            st.session_state.questao_atual = gerar_questao()
            st.session_state.status_resposta = None
            st.session_state.escolha = None
            st.session_state.aula_gerada = None

    q = st.session_state.questao_atual

    st.info(f"**Banca:** {q['banca']} | **Concurso:** {q['concurso']} | **Matéria:** {q['materia']} — *{q.get('assunto', '')}*")
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
                    "INSERT INTO questoes (data, concurso, banca, materia, enunciado, gabarito, resposta_usuario, acertou) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), q["concurso"], q["banca"], q["materia"], q["enunciado"], q["gabarito"], escolha, acertou)
                )
                conn.commit()
                st.rerun()

        with col2:
            if st.button("🤷 Não sei o assunto (Abrir Aula Completa)", type="secondary", use_container_width=True):
                st.session_state.escolha = "NÃO SEI"
                st.session_state.status_resposta = "nao_sei"
                
                cursor.execute(
                    "INSERT INTO questoes (data, concurso, banca, materia, enunciado, gabarito, resposta_usuario, acertou) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), q["concurso"], q["banca"], q["materia"], q["enunciado"], q["gabarito"], "NÃO SEI", 0)
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
                with st.spinner("Construindo aula aprofundada com teoria, análise de alternativas e padrão de banca..."):
                    st.session_state.aula_gerada = gerar_aula_profunda(q)
            
            st.markdown(st.session_state.aula_gerada)

        st.markdown("---")
        if st.button("Próxima Questão ➡️", type="primary", use_container_width=True):
            with st.spinner("Buscando próxima questão adaptada ao seu desempenho..."):
                st.session_state.questao_atual = gerar_questao()
                st.session_state.status_resposta = None
                st.session_state.escolha = None
                st.session_state.aula_gerada = None
                st.rerun()

# ====================================================
# TELA 2: DASHBOARD COMPLETO & ESTIMATIVA DE CAPACITAÇÃO
# ====================================================
elif menu == "📊 Dashboard Completo":
    st.title("📊 Painel de Desempenho & Estimativa de Capacitação")
    
    hoje = date.today()
    hoje_str = hoje.strftime("%Y-%m-%d")
    inicio_semana = (hoje - timedelta(days=7)).strftime("%Y-%m-%d")
    inicio_mes = (hoje - timedelta(days=30)).strftime("%Y-%m-%d")

    # Consultas temporais
    total_hoje = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ?", (hoje_str,)).fetchone()[0]
    acertos_hoje = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ? AND acertou = 1", (hoje_str,)).fetchone()[0]

    total_semana = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ?", (inicio_semana,)).fetchone()[0]
    acertos_semana = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ? AND acertou = 1", (inicio_semana,)).fetchone()[0]

    total_mes = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ?", (inicio_mes,)).fetchone()[0]
    acertos_mes = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data >= ? AND acertou = 1", (inicio_mes,)).fetchone()[0]

    total_acumulado = cursor.execute("SELECT COUNT(*) FROM questoes").fetchone()[0]
    acertos_acumulado = cursor.execute("SELECT COUNT(*) FROM questoes WHERE acertou = 1").fetchone()[0]

    # Taxas
    taxa_hoje = (acertos_hoje / total_hoje * 100) if total_hoje > 0 else 0
    taxa_semana = (acertos_semana / total_semana * 100) if total_semana > 0 else 0
    taxa_mes = (acertos_mes / total_mes * 100) if total_mes > 0 else 0
    taxa_geral = (acertos_acumulado / total_acumulado * 100) if total_acumulado > 0 else 0

    # 1. Cards de Volume Temporal
    st.subheader("📅 Volume de Treino por Período")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hoje", f"{total_hoje} q.", f"{taxa_hoje:.1f}% acerto")
    c2.metric("Últimos 7 Dias", f"{total_semana} q.", f"{taxa_semana:.1f}% acerto")
    c3.metric("Últimos 30 Dias", f"{total_mes} q.", f"{taxa_mes:.1f}% acerto")
    c4.metric("Total Acumulado", f"{total_acumulado} q.", f"{taxa_geral:.1f}% acerto")

    st.markdown("---")

    # 2. Estimativa de Capacitação para a Prova
    st.subheader("🎯 Termômetro de Prontidão para Aprovação")
    
    META_COMPETITIVA = 500
    progresso = min(total_acumulado / META_COMPETITIVA, 1.0)
    restantes = max(META_COMPETITIVA - total_acumulado, 0)
    
    st.write(f"**Progresso até a base competitiva recomendada ({META_COMPETITIVA} questões resolvidas):**")
    st.progress(progresso)
    
    col_cap1, col_cap2 = st.columns(2)
    with col_cap1:
        st.info(f"📌 **Faltam {restantes} questões** para atingir o volume ótimo de maturidade nas bancas FGV/Cesgranrio.")
    with col_cap2:
        if taxa_geral >= 80 and total_acumulado >= 300:
            st.success("🟢 **Status:** Nível Competitivo de Alta Performance!")
        elif taxa_geral >= 65:
            st.warning("🟡 **Status:** Nível Intermediário — Mantenha o ritmo diário.")
        else:
            st.error("🔴 **Status:** Fase de Construção de Base — Priorize revisar os temas com botão 'Não sei'.")

    st.markdown("---")

    # 3. Tabela Detalhada por Matéria
    st.subheader("📊 Rendimento e Diagnóstico por Matéria")
    stats_materia = cursor.execute("""
        SELECT 
            materia, 
            COUNT(*) as total, 
            SUM(CASE WHEN acertou = 1 THEN 1 ELSE 0 END) as acertos,
            SUM(CASE WHEN resposta_usuario = 'NÃO SEI' THEN 1 ELSE 0 END) as duvidas
        FROM questoes 
        GROUP BY materia
        ORDER BY (CAST(SUM(CASE WHEN acertou = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) ASC
    """).fetchall()

    if stats_materia:
        tabela = []
        for mat, tot, ac, duv in stats_materia:
            acertos = ac or 0
            taxa = (acertos / tot) * 100
            status = "🔴 Prioridade Alta (Fraco)" if taxa < 60 else ("🟡 Atenção" if taxa < 80 else "🟢 Dominado")
            tabela.append({
                "Matéria": mat,
                "Total de Questões": tot,
                "Acertos": acertos,
                "Aulas Solicitadas": duv,
                "Aproveitamento": f"{taxa:.1f}%",
                "Diagnóstico": status
            })
        st.table(tabela)
    else:
        st.info("Resolva suas primeiras questões para liberar o mapa detalhado por matéria.")
