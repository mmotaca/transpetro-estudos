from datetime import date, datetime
import json
import os
import pandas as pd
import requests
import streamlit as st
from supabase import Client, create_client

# ----------------------------------------------------
# 1. CONFIGURAÇÕES SEGURAS
# ----------------------------------------------------
raw_gemini_key = st.secrets.get(
    "GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", "")
)
GEMINI_API_KEY = (
    raw_gemini_key.strip().strip('"').strip("'") if raw_gemini_key else ""
)

raw_supa_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_URL = (
    raw_supa_url.strip().strip('"').strip("'") if raw_supa_url else ""
)

raw_supa_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPABASE_KEY = (
    raw_supa_key.strip().strip('"').strip("'") if raw_supa_key else ""
)

if not GEMINI_API_KEY:
  st.error("🔑 Configure a chave GEMINI_API_KEY no Secrets do Streamlit!")
  st.stop()


# Inicialização do Supabase
@st.cache_resource
def get_supabase():
  if SUPABASE_URL and SUPABASE_KEY:
    try:
      return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
      return None
  return None


supabase = get_supabase()


# ----------------------------------------------------
# 2. BANCO DE DADOS (SUPABASE)
# ----------------------------------------------------
def carregar_dados():
  if not supabase:
    return pd.DataFrame()
  try:
    res = supabase.table("questoes").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()
  except Exception:
    return pd.DataFrame()


def registrar_resposta(q, resposta, acertou, cargo_selecionado):
  if not supabase:
    return
  linha = {
      "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "concurso": str(q.get("concurso", "")),
      "cargo": str(q.get("cargo", cargo_selecionado)),
      "banca": str(q.get("banca", "")),
      "materia": str(q.get("materia", "")),
      "enunciado": str(q.get("enunciado", "")),
      "gabarito": str(q.get("gabarito", "")),
      "resposta_usuario": str(resposta),
      "acertou": int(acertou),
  }
  try:
    supabase.table("questoes").insert(linha).execute()
  except Exception as e:
    st.warning(f"Aviso ao gravar histórico: {e}")


# ----------------------------------------------------
# 3. CARGOS E DISCIPLINAS
# ----------------------------------------------------
CARGOS_INFO = {
    "Dataprev - Analista de TI": {
        "concurso": "Dataprev",
        "banca": "FGV",
        "materias": (
            "Banco de Dados, Governança de TI (COBIT/ITIL), Engenharia de"
            " Software, Segurança da Informação, Raciocínio Lógico e Português."
        ),
    },
    "Transpetro - Analista SAP": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": (
            "Módulos SAP (ECC/S4HANA, MM, PM, FI, CO, ABAP), Integração de"
            " Sistemas, Governança de TI, Raciocínio Lógico e Português."
        ),
    },
    "Transpetro - Mecânico de Manutenção": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": (
            "Mecânica dos Fluidos, Bombas e Compressores, Manutenção"
            " Preditiva/Preventiva, Soldagem, Ensaios Não Destrutivos,"
            " Metrologia, Elementos de Máquinas, Desenho Técnico, Raciocínio"
            " Lógico e Português."
        ),
    },
}


# ----------------------------------------------------
# 4. CHAMADA DIRETA À API GEMINI (SEM BIBLIOTECAS BUGADAS)
# ----------------------------------------------------
def chamar_gemini_api(prompt, formato_json=False):
  modelos = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
  ultimo_erro = ""

  for mod in modelos:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    if formato_json:
      payload["generationConfig"] = {"responseMimeType": "application/json"}

    try:
      resp = requests.post(url, headers=headers, json=payload, timeout=25)
      if resp.status_code == 200:
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
      else:
        ultimo_erro = f"HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
      ultimo_erro = str(e)

  st.error(f"❌ Erro ao conectar com o Gemini: {ultimo_erro}")
  st.stop()


def limpar_json(texto):
  t = texto.strip()
  if t.startswith("```json"):
    t = t[7:]
  elif t.startswith("```"):
    t = t[3:]
  if t.endswith("```"):
    t = t[:-3]
  t = t.strip()
  try:
    return json.loads(t)
  except Exception:
    i1 = t.find("{")
    i2 = t.rfind("}") + 1
    if i1 != -1 and i2 > i1:
      return json.loads(t[i1:i2])
    raise ValueError("Resposta da IA fora do padrão JSON.")


# ----------------------------------------------------
# 5. GERADOR DE QUESTÕES
# ----------------------------------------------------
def gerar_questao(cargo_selecionado, pedido_extra=""):
  df = carregar_dados()
  contexto = "Início do ciclo adaptativo"

  if cargo_selecionado == "Ciclo Automático (Todos os Cargos)":
    if not df.empty and "acertou" in df.columns:
      df_ok = df[df["resposta_usuario"] != "NÃO SEI"]
      if not df_ok.empty:
        agrup = (
            df_ok.groupby(["cargo", "materia"])["acertou"].mean().reset_index()
        )
        pior = agrup.sort_values(by="acertou").iloc[0]
        alvo = (
            pior["cargo"]
            if pior["cargo"] in CARGOS_INFO
            else "Dataprev - Analista de TI"
        )
        contexto = f"Reforçar cargo {alvo} na matéria {pior['materia']}"
      else:
        alvo = "Dataprev - Analista de TI"
    else:
      alvo = "Dataprev - Analista de TI"
  else:
    alvo = cargo_selecionado
    if not df.empty and "cargo" in df.columns:
      df_c = df[(df["cargo"] == alvo) & (df["resposta_usuario"] != "NÃO SEI")]
      if not df_c.empty:
        agrup = df_c.groupby("materia")["acertou"].mean().reset_index()
        pior = agrup.sort_values(by="acertou").iloc[0]
        contexto = f"Reforçar matéria {pior['materia']}"

  info = CARGOS_INFO[alvo]
  extra = f"\nPedido do aluno: {pedido_extra}" if pedido_extra.strip() else ""

  prompt = f"""
    Atue como Diretor Virtual de Estudos Especialista em Concursos Públicos.
    Concurso: {info['concurso']}
    Cargo: {alvo}
    Banca: {info['banca']}
    Ementa: {info['materias']}
    Diretriz: {contexto} {extra}

    REGRAS OBRIGATÓRIAS:
    1. Todas as siglas devem vir com o significado por extenso entre parênteses.
    2. O campo 'explicacao_detalhada' deve analisar a alternativa correta e comentar uma a uma todas as incorretas.

    Retorne apenas JSON válido com esta estrutura:
    {{
      "concurso": "{info['concurso']}",
      "cargo": "{alvo}",
      "banca": "{info['banca']}",
      "materia": "Nome da Disciplina",
      "assunto": "Tópico Específico",
      "enunciado": "Texto da questão",
      "opcoes": {{"A": "Opção A", "B": "Opção B", "C": "Opção C", "D": "Opção D", "E": "Opção E"}},
      "gabarito": "A",
      "explicacao_detalhada": "Análise detalhada da alternativa correta e de cada alternativa incorreta com siglas por extenso."
    }}
    """

  texto_resposta = chamar_gemini_api(prompt, formato_json=True)
  return limpar_json(texto_resposta)


# ----------------------------------------------------
# 6. GERADOR DE AULA COMPLETA
# ----------------------------------------------------
def gerar_aula(q):
  prompt = f"""
    Professor titular preparando candidato para a banca {q['banca']} no cargo {q.get('cargo', q['concurso'])}.
    O aluno marcou 'Não Sei' no assunto:
    Matéria: {q['materia']} | Assunto: {q.get('assunto', '')}
    Enunciado: {q['enunciado']}
    Alternativas: {json.dumps(q['opcoes'], ensure_ascii=False)}
    Gabarito: {q['gabarito']}

    Escreva todas as siglas por extenso entre parênteses.
    Estruture a aula em Markdown com:
    ## 🏛️ 1. Teoria Completa do Conceito
    ## 🔍 2. Análise Alternativa por Alternativa
    ## ⚡ 3. Padrão da Banca ({q['banca']}) e Armadilhas
    ## 🧠 4. Resumo Prático e Regra de Ouro
    """
  return chamar_gemini_api(prompt, formato_json=False)


# ----------------------------------------------------
# 7. INTERFACE STREAMLIT
# ----------------------------------------------------
st.set_page_config(
    page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide"
)

st.sidebar.title("📚 Menu de Estudos")
menu = st.sidebar.radio(
    "Ir para:", ["📝 Treino de Questões", "📊 Painel de Desempenho"]
)

st.sidebar.markdown("---")
cargo_selecionado = st.sidebar.selectbox(
    "🎯 Foco Atual:",
    ["Ciclo Automático (Todos os Cargos)"] + list(CARGOS_INFO.keys()),
)

pedido_usuario = st.sidebar.text_area(
    "💬 Pedido Específico (Opcional):",
    placeholder="Ex: Questão de Crase FGV / Bombas Industriais",
)

if st.sidebar.button("🔄 Gerar Nova Questão", use_container_width=True):
  st.session_state.questao_atual = None
  st.session_state.status_resposta = None
  st.session_state.escolha = None
  st.session_state.aula_gerada = None
  st.rerun()

# --- ABA 1: TREINO ---
if menu == "📝 Treino de Questões":
  st.title("🎯 Treino de Questões Adaptativo")

  if (
      "cargo_memoria" not in st.session_state
      or st.session_state.cargo_memoria != cargo_selecionado
  ):
    st.session_state.cargo_memoria = cargo_selecionado
    st.session_state.questao_atual = None

  if st.session_state.get("questao_atual") is None:
    with st.spinner("Preparando questão inédita..."):
      st.session_state.questao_atual = gerar_questao(
          cargo_selecionado, pedido_usuario
      )
      st.session_state.status_resposta = None
      st.session_state.escolha = None
      st.session_state.aula_gerada = None

  q = st.session_state.questao_atual

  st.info(
      f"📌 **Cargo:** {q.get('cargo', q['concurso'])} | **Banca:** {q['banca']}"
      f" | **Matéria:** {q['materia']} — *{q.get('assunto', '')}*"
  )
  st.markdown(f"### {q['enunciado']}")

  travado = st.session_state.status_resposta is not None
  escolha = st.radio(
      "Selecione uma resposta:",
      list(q["opcoes"].keys()),
      format_func=lambda k: f"{k}) {q['opcoes'][k]}",
      disabled=travado,
  )

  col1, col2 = st.columns(2)

  if not travado:
    with col1:
      if st.button(
          "✅ Confirmar Resposta", type="primary", use_container_width=True
      ):
        st.session_state.escolha = escolha
        acertou = 1 if escolha == q["gabarito"] else 0
        st.session_state.status_resposta = (
            "acertou" if acertou == 1 else "errou"
        )
        registrar_resposta(q, escolha, acertou, cargo_selecionado)
        st.rerun()

    with col2:
      if st.button(
          "🤷 Não sei o assunto (Aula)",
          type="secondary",
          use_container_width=True,
      ):
        st.session_state.escolha = "NÃO SEI"
        st.session_state.status_resposta = "nao_sei"
        registrar_resposta(q, "NÃO SEI", 0, cargo_selecionado)
        st.rerun()

  if travado:
    st.markdown("---")
    exp = q.get("explicacao_detalhada", "")

    if st.session_state.status_resposta == "acertou":
      st.success(
          f"🎉 **Parabéns, você acertou!** Gabarito oficial:"
          f" **{q['gabarito']}**."
      )
      st.markdown("### 📝 Comentário das Alternativas:")
      st.markdown(exp)
    elif st.session_state.status_resposta == "errou":
      st.error(
          f"❌ **Resposta incorreta.** Você marcou"
          f" **{st.session_state.escolha}**, mas o gabarito oficial é"
          f" **{q['gabarito']}**."
      )
      st.markdown("### 📝 Comentário das Alternativas:")
      st.markdown(exp)
    elif st.session_state.status_resposta == "nao_sei":
      st.warning(
          f"💡 **Aula Teórica Completa!** Gabarito oficial: **{q['gabarito']}**."
      )
      if st.session_state.aula_gerada is None:
        with st.spinner("Construindo explicação passo a passo..."):
          st.session_state.aula_gerada = gerar_aula(q)
      st.markdown(st.session_state.aula_gerada)

    st.markdown("---")
    if st.button("Próxima Questão ➡️", type="primary", use_container_width=True):
      st.session_state.questao_atual = None
      st.session_state.status_resposta = None
      st.session_state.escolha = None
      st.session_state.aula_gerada = None
      st.rerun()

# --- ABA 2: PAINEL ---
elif menu == "📊 Painel de Desempenho":
  st.title("📊 Painel de Desempenho dos Concursos")

  df = carregar_dados()

  if df.empty or "acertou" not in df.columns:
    st.info("Nenhuma questão registrada ainda. Comece a praticar no menu!")
  else:
    df["dt"] = pd.to_datetime(df["data"], errors="coerce")

    tot = len(df)
    ac = int(df["acertou"].sum())
    taxa = (ac / tot * 100) if tot > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Resolvido", f"{tot} questões")
    c2.metric("Total de Acertos", f"{ac} acertos")
    c3.metric("Aproveitamento Geral", f"{taxa:.1f}%")

    st.markdown("---")
    st.subheader("🎯 Desempenho por Concurso e Cargo")

    tab1, tab2, tab3 = st.tabs(
        ["🏢 Dataprev (TI)", "🛢️ Transpetro (SAP)", "⚙️ Transpetro (Mecânica)"]
    )

    def mostrar_cargo(cargo_nome, meta=350):
      df_c = df[
          (df["cargo"] == cargo_nome)
          | (df["concurso"] == cargo_nome.split(" - ")[0])
      ]
      tot_c = len(df_c)
      ac_c = int(df_c["acertou"].sum()) if tot_c > 0 else 0
      duv_c = len(df_c[df_c["resposta_usuario"] == "NÃO SEI"])
      taxa_c = (ac_c / tot_c * 100) if tot_c > 0 else 0

      m1, m2, m3, m4 = st.columns(4)
      m1.metric("Resolvidas", f"{tot_c}")
      m2.metric("Acertos", f"{ac_c}")
      m3.metric("Aulas Abertas", f"{duv_c}")
      m4.metric("Aproveitamento", f"{taxa_c:.1f}%")

      st.progress(min(tot_c / meta, 1.0))
      st.caption(f"Meta de questões recomendadas: {tot_c}/{meta}")

      if tot_c > 0:
        st.markdown("##### 📌 Desempenho por Matéria:")
        resumo = (
            df_c.groupby("materia")
            .agg(
                total=("acertou", "count"),
                acertos=("acertou", "sum"),
            )
            .reset_index()
        )
        resumo["taxa"] = (resumo["acertos"] / resumo["total"]) * 100
        resumo["Aproveitamento"] = resumo["taxa"].map(lambda x: f"{x:.1f}%")
        st.dataframe(
            resumo[["materia", "total", "acertos", "Aproveitamento"]],
            use_container_width=True,
        )

    with tab1:
      mostrar_cargo("Dataprev - Analista de TI", 400)
    with tab2:
      mostrar_cargo("Transpetro - Analista SAP", 350)
    with tab3:
      mostrar_cargo("Transpetro - Mecânico de Manutenção", 350)
