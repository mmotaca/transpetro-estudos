import streamlit as st
import sqlite3
import json
from datetime import datetime, date
from google import genai
from google.genai import types

# ----------------------------------------------------
# 1. CONFIGURAÇÃO DA API GEMINI
# ----------------------------------------------------
GEMINI_API_KEY = "AQ.Ab8RN6Kw-oIgFWAmc6mDWOjMNpvC3DG_LGhoBpqtkBfeIUcsHA" 
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
# 3. FUNÇÃO PARA GERAR NOVA QUESTÃO
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
    1. Dataprev (Analista de Informação) - Banca FGV
    2. Transpetro (Analista SAP / Mecânico de Manutenção) - Banca Cesgranrio
    3. Base Geral: Português e Raciocínio Lógico-Matemático.
    
    Perfil do Aluno: TDAH (frases concisas, direct, foco em palavras-chave em negrito).
    Status do Aluno: {contexto_fraqueza}.

    Gere UMA questão inédita com alto rigor técnico da banca correspondente.
    Retorne ESTRITAMENTE em formato JSON com o seguinte schema:
    {{
        "concurso": "Dataprev ou Transpetro",
        "banca": "FGV ou Cesgranrio",
        "materia": "Nome da Matéria",
        "assunto": "Tópico Específico",
        "enunciado": "Texto da questão claro e objetivo",
        "opcoes": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
        "gabarito": "A, B, C, D ou E",
        "explicacao_rapida": "Explicação direta em tópicos destacando a lógica da banca.",
        "explicacao_didatica": "Aula completa e passo a passo explicando o conceito teórico para quem não sabe o assunto."
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
# 4. INTERFACE E ABAS (STREAMLIT)
# ----------------------------------------------------
st.set_page_config(page_title="Tutor Adaptativo", page_icon="🎯", layout="wide")

aba_estudo, aba_stats = st.tabs(["📝 Treino & Questões", "📊 Painel de Estatísticas Detalhadas"])

# ==========================================
# ABA 1: ÁREA DE ESTUDOS
# ==========================================
with aba_estudo:
    st.title("🎯 Treino de Questões Adaptativo")
    
    if "questao_atual" not in st.session_state:
        with st.spinner("Gerando questão sob medida..."):
            st.session_state.questao_atual = gerar_questao()
            st.session_state.status_resposta = None  # 'acertou', 'errou', 'nao_sei'
            st.session_state.escolha = None

    q = st.session_state.questao_atual

    # Card informativo
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

    # Botões de Ação
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
            if st.button("🤷 Não sei o assunto (Aprender teoria)", type="secondary", use_container_width=True):
                st.session_state.escolha = "NÃO SEI"
                st.session_state.status_resposta = "nao_sei"
                
                cursor.execute(
                    "INSERT INTO questoes (data, concurso, banca, materia, enunciado, gabarito, resposta_usuario, acertou) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), q["concurso"], q["banca"], q["materia"], q["enunciado"], q["gabarito"], "NÃO SEI", 0)
                )
                conn.commit()
                st.rerun()

    # Exibição do Feedback e Explicações
    if disabled:
        st.markdown("---")
        if st.session_state.status_resposta == "acertou":
            st.success(f"🎉 **ACERTOU!** O gabarito oficial é **{q['gabarito']}**.")
            st.write(q["explicacao_rapida"])
        elif st.session_state.status_resposta == "errou":
            st.error(f"❌ **ERROU!** Você marcou **{st.session_state.escolha}**, mas o gabarito oficial é **{q['gabarito']}**.")
            st.write(q["explicacao_rapida"])
        elif st.session_state.status_resposta == "nao_sei":
            st.warning(f"💡 **Modo Aula Ativado!** O gabarito correto desta questão é **{q['gabarito']}**.")
            st.markdown("### 📖 Entenda o conceito passo a passo:")
            st.write(q.get("explicacao_didatica", q["explicacao_rapida"]))

        st.markdown("---")
        if st.button("Próxima Questão ➡️", type="primary", use_container_width=True):
            with st.spinner("Buscando próxima questão adaptada ao seu desempenho..."):
                st.session_state.questao_atual = gerar_questao()
                st.session_state.status_resposta = None
                st.session_state.escolha = None
                st.rerun()

# ==========================================
# ABA 2: ESTATÍSTICAS DETALHADAS
# ==========================================
with aba_stats:
    st.title("📊 Painel de Desempenho & Diagnóstico")
    
    hoje_str = date.today().strftime("%Y-%m-%d")
    
    # Métricas gerais
    total_geral = cursor.execute("SELECT COUNT(*) FROM questoes").fetchone()[0]
    total_hoje = cursor.execute("SELECT COUNT(*) FROM questoes WHERE data LIKE ?", (f"{hoje_str}%",)).fetchone()[0]
    acertos_geral = cursor.execute("SELECT COUNT(*) FROM questoes WHERE acertou = 1").fetchone()[0]
    acertos_hoje = cursor.execute("SELECT COUNT(*) FROM questoes WHERE acertou = 1 AND data LIKE ?", (f"{hoje_str}%",)).fetchone()[0]
    nao_sei_count = cursor.execute("SELECT COUNT(*) FROM questoes WHERE resposta_usuario = 'NÃO SEI'").fetchone()[0]

    taxa_acerto_geral = (acertos_geral / total_geral * 100) if total_geral > 0 else 0
    taxa_acerto_hoje = (acertos_hoje / total_hoje * 100) if total_hoje > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Questões Hoje", total_hoje, f"{taxa_acerto_hoje:.1f}% acerto")
    c2.metric("Total Acumulado", total_geral, f"{taxa_acerto_geral:.1f}% acerto")
    c3.metric("Total de Acertos", acertos_geral)
    c4.metric("Aulas Solicitadas ('Não Sei')", nao_sei_count)

    st.markdown("---")
    st.subheader("📈 Rendimento por Matéria")
    
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
        dados_tabela = []
        for mat, tot, ac, duv in stats_materia:
            acertos = ac or 0
            taxa = (acertos / tot) * 100
            status = "🔴 Prioridade Alta (Fraco)" if taxa < 60 else ("🟡 Atenção" if taxa < 80 else "🟢 Dominado")
            dados_tabela.append({
                "Matéria": mat,
                "Total": tot,
                "Acertos": acertos,
                "Dúvidas / Pulos": duv,
                "Taxa de Acerto": f"{taxa:.1f}%",
                "Diagnóstico": status
            })
        st.table(dados_tabela)
    else:
        st.info("Resolva algumas questões para liberar os gráficos e o diagnóstico de fraquezas.")
