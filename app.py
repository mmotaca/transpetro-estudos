import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, date, timedelta
from supabase import create_client, Client
from google import genai
from google.genai import types

# ----------------------------------------------------
# 1. CONFIGURAÇÕES (GEMINI + SUPABASE)
# ----------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))

client = genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# ----------------------------------------------------
# 2. OPERAÇÕES NO BANCO SUPABASE
# ----------------------------------------------------
def carregar_dados():
    try:
        response = supabase.table("questoes").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def salvar_resposta_supabase(nova_linha):
    try:
        supabase.table("questoes").insert(nova_linha).execute()
    except Exception as e:
        st.error(f"Erro ao salvar no banco Supabase: {e}")

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
# 4. GERADOR DE QUESTÕES COM PEDIDO PERSONALIZADO
# ----------------------------------------------------
def gerar_questao(cargo_selecionado, pedido_personalizado=""):
    df = carregar_dados()
    contexto_fraqueza = "Início do ciclo adaptativo"
    
    if cargo_selecionado == "Ciclo Automático (Todos os Cargos)":
        if not df.empty and "acertou" in df.columns:
            df_validas = df[df["resposta_usuario"] != "NÃO SEI"]
            if not df_validas.empty:
                agrupado = df_validas.groupby(["cargo", "materia"])["acertou"].mean().reset_index()
                pior = agrupado.sort_values(by="acertou").iloc[0]
                cargo_alvo = pior["cargo"] if pior["cargo"] in CARGOS_INFO else "Dataprev - Analista de TI"
                contexto_fraqueza = f"Foco prioritário de erro no cargo {cargo_alvo} na matéria {pior['materia']}"
            else:
                cargo_alvo = "Dataprev - Analista de TI"
        else:
            cargo_alvo = "Dataprev - Analista de TI"
    else:
        cargo_alvo = cargo_selecionado
        if not df.empty and "cargo" in df.columns:
            df_cargo = df[(df["cargo"] == cargo_alvo) & (df["resposta_usuario"] != "NÃO SEI")]
            if not df_cargo.empty:
                agrupado = df_cargo.groupby("materia")["acertou"].mean().reset_index()
                pior = agrupado.sort_values(by="acertou").iloc[0]
                contexto_fraqueza = f"Foco de erro no cargo {cargo_alvo}: matéria {pior['materia']}"

    info = CARGOS_INFO[cargo_alvo]

    instrucao_extra = ""
    if pedido_personalizado and pedido_personalizado.strip() != "":
        instrucao_extra = f"\n⚠️ PEDIDO DIRETO DO ALUNO: '{pedido_personalizado.strip()}'. Cumpra estritamente essa solicitação sobre o tema/dificuldade."

    prompt_instrucao = f"""
    Atue como Diretor Virtual de Estudos Especialista em Concursos Públicos.
    Concurso: {info['concurso']}
    Cargo: {cargo_alvo}
    Banca Examinadora: {info['banca']}
    Ementa do Cargo: {info['materias']}
    Status do Aluno: {contexto_fraqueza}
    {instrucao_extra}

    Gere UMA questão inédita no estilo autêntico da banca examinadora.
    Retorne ESTRITAMENTE em formato JSON com o seguinte schema:
    {{
        "concurso": "{info['concurso']}",
        "cargo": "{cargo_alvo}",
        "banca": "{info['banca']}",
        "materia": "Nome da Matéria",
        "assunto": "Tópico Específico",
        "enunciado": "Texto claro e direto da questão",
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
    Tópicos rápidos ou mnemônico para memorizar e acertar em 30 segundos na prova.
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

st.sidebar.markdown("---")
st.sidebar.subheader("💬 Pedido Especial para a IA")
pedido_usuario = st.sidebar.text_area(
    "Instrução personalizada (opcional):",
    placeholder="Ex: Quero questão de COBIT 2019 / Foco em bombas centrífugas / Pegadinha FGV",
    help="Se preenchido, a IA priorizará sua instrução."
)

if st.sidebar.button("🔄 Aplicar Pedido / Nova Questão", use_container_width=True):
    st.session_state.questao_atual = None
    st.session_state.status_resposta = None
    st.session_state.escolha = None
    st.session_state.aula_gerada = None
    st.rerun()

# ====================================================
# TELA 1: ÁREA DE QUESTÕES
# ====================================================
if menu == "📝 Treino de Questões":
    st.title("🎯 Treino de Questões Adaptativo")
    
    if "cargo_atual_memoria" not in st.session_state or st.session_state.cargo_atual_memoria != cargo_selecionado:
        st.session_state.cargo_atual_memoria = cargo_selecionado
        st.session_state.questao_atual = None

    if st.session_state.get("questao_atual") is None:
        with st.spinner(f"Gerando questão inédita para: {cargo_selecionado}..."):
            st.session_state.questao_atual = gerar_questao(cargo_selecionado, pedido_usuario)
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
                
                salvar_resposta_supabase({
                    "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "concurso": q["concurso"],
                    "cargo": q.get("cargo", cargo_selecionado),
                    "banca": q["banca"],
                    "materia": q["materia"],
                    "enunciado": q["enunciado"],
                    "gabarito": q["gabarito"],
                    "resposta_usuario": escolha,
                    "acertou": acertou
                })
                st.rerun()

        with col2:
            if st.button("🤷 Não sei o assunto (Abrir Aula Completa)", type="secondary", use_container_width=True):
                st.session_state.escolha = "NÃO SEI"
                st.session_state.status_resposta = "nao_sei"
                
                salvar_resposta_supabase({
                    "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "concurso": q["concurso"],
                    "cargo": q.get("cargo", cargo_selecionado),
                    "banca": q["banca"],
                    "materia": q["materia"],
                    "enunciado": q["enunciado"],
                    "gabarito": q["gabarito"],
                    "resposta_usuario": "NÃO SEI",
                    "acertou": 0
                })
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
                st.session_state.questao_atual = gerar_questao(cargo_selecionado, pedido_usuario)
                st.session_state.status_resposta = None
                st.session_state.escolha = None
                st.session_state.aula_gerada = None
                st.rerun()

# ====================================================
# TELA 2: DASHBOARD GERAL E POR CARGO
# ====================================================
elif menu == "📊 Dashboard Geral & Por Cargo":
    st.title("📊 Painel de Desempenho & Panorama dos 3 Concursos")
    
    df = carregar_dados()
    
    if df.empty or "acertou" not in df.columns:
        st.info("Nenhum dado registrado no Supabase ainda. Resolva algumas questões para sincronizar!")
    else:
        df["data_dt"] = pd.to_datetime(df["data"], errors="coerce")
        hoje_dt = pd.to_datetime(date.today())
        sete_dias_dt = hoje_dt - timedelta(days=7)
        trinta_dias_dt = hoje_dt - timedelta(days=30)

        df_hoje = df[df["data_dt"] >= hoje_dt]
        df_semana = df[df["data_dt"] >= sete_dias_dt]
        df_mes = df[df["data_dt"] >= trinta_dias_dt]

        tot_h = len(df_hoje)
        tot_s = len(df_semana)
        tot_m = len(df_mes)
        tot_g = len(df)

        ac_h = int(df_hoje["acertou"].sum()) if tot_h > 0 else 0
        ac_s = int(df_semana["acertou"].sum()) if tot_s > 0 else 0
        ac_m = int(df_mes["acertou"].sum()) if tot_m > 0 else 0
        ac_g = int(df["acertou"].sum()) if tot_g > 0 else 0

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

        def renderizar_painel_cargo_df(nome_cargo, meta_questoes=300):
            df_c = df[(df["cargo"] == nome_cargo) | (df["concurso"] == nome_cargo.split(" - ")[0])]
            tot = len(df_c)
            ac = int(df_c["acertou"].sum()) if tot > 0 else 0
            duv = len(df_c[df_c["resposta_usuario"] == "NÃO SEI"])

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
            if tot > 0:
                stats_mat = df_c.groupby("materia").agg(
                    total=("acertou", "count"),
                    acertos=("acertou", "sum"),
                    duvidas=("resposta_usuario", lambda x: (x == "NÃO SEI").sum())
                ).reset_index()

                stats_mat["taxa"] = (stats_mat["acertos"] / stats_mat["total"]) * 100
                stats_mat = stats_mat.sort_values(by="taxa", ascending=True)

                tabela = []
                for _, row in stats_mat.iterrows():
                    tx = row["taxa"]
                    status_txt = "🔴 Prioridade Alta" if tx < 60 else ("🟡 Atenção" if tx < 80 else "🟢 Dominado")
                    tabela.append({
                        "Matéria": row["materia"],
                        "Total de Questões": int(row["total"]),
                        "Acertos": int(row["acertos"]),
                        "Aulas Solicitadas": int(row["duvidas"]),
                        "Aproveitamento": f"{tx:.1f}%",
                        "Diagnóstico": status_txt
                    })
                st.table(tabela)
            else:
                st.caption("Nenhuma questão resolvida para este cargo ainda.")

        with tab_dataprev:
            renderizar_painel_cargo_df("Dataprev - Analista de TI", meta_questoes=400)

        with tab_sap:
            renderizar_painel_cargo_df("Transpetro - Analista SAP", meta_questoes=350)

        with tab_mecanico:
            renderizar_painel_cargo_df("Transpetro - Mecânico de Manutenção", meta_questoes=350)
