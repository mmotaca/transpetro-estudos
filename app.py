from datetime import datetime
import json
import os
import pandas as pd
import requests
import streamlit as st
from supabase import create_client

# ----------------------------------------------------
# 1. CONFIGURAÇÃO E ESTADO INICIAL
# ----------------------------------------------------
st.set_page_config(
    page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide"
)

defaults = {
    "questao_atual": None,
    "status_resposta": None,
    "escolha": None,
    "aula_gerada": None,
    "cargo_memoria": None,
}
for k, v in defaults.items():
  if k not in st.session_state:
    st.session_state[k] = v

GROQ_KEY = str(
    st.secrets.get(
        "GROQ_API_KEY", os.environ.get("GROQ_API_KEY", "")
    )
).strip().strip('"').strip("'")
SUPA_URL = str(
    st.secrets.get(
        "SUPABASE_URL", os.environ.get("SUPABASE_URL", "")
    )
).strip().strip('"').strip("'")
SUPA_KEY = str(
    st.secrets.get(
        "SUPABASE_KEY", os.environ.get("SUPABASE_KEY", "")
    )
).strip().strip('"').strip("'")


@st.cache_resource
def init_supabase():
  if SUPA_URL and SUPA_KEY:
    try:
      return create_client(SUPA_URL, SUPA_KEY)
    except Exception:
      return None
  return None


supabase = init_supabase()


# ----------------------------------------------------
# 2. DADOS E EMENTAS DOS CARGOS
# ----------------------------------------------------
CARGOS_INFO = {
    "Dataprev - Analista de TI": {
        "concurso": "Dataprev",
        "banca": "FGV",
        "materias": [
            "Banco de Dados",
            "Governança de TI (COBIT/ITIL)",
            "Engenharia de Software",
            "Segurança da Informação",
            "Raciocínio Lógico",
            "Português",
        ],
    },
    "Transpetro - Analista SAP": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": [
            "Módulos SAP (ECC/S4HANA, MM, PM, FI, CO, ABAP)",
            "Integração de Sistemas",
            "Governança de TI",
            "Raciocínio Lógico",
            "Português",
        ],
    },
    "Transpetro - Mecânico de Manutenção": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": [
            "Mecânica dos Fluidos",
            "Bombas e Compressores",
            "Manutenção Preditiva/Preventiva",
            "Soldagem",
            "Ensaios Não Destrutivos",
            "Metrologia",
            "Elementos de Máquinas",
            "Desenho Técnico",
            "Raciocínio Lógico",
            "Português",
        ],
    },
}

QUESTAO_FALLBACK = {
    "concurso": "Transpetro",
    "cargo": "Transpetro - Analista SAP",
    "banca": "Cesgranrio",
    "materia": "Módulos SAP",
    "assunto": "Integração MM e FI",
    "enunciado": (
        "No sistema SAP ECC, qual módulo principal é responsável pela gestão de"
        " compras e estoques e se integra ao módulo FI no recebimento de"
        " faturas?"
    ),
    "opcoes": {
        "A": "SAP SD (Sales and Distribution)",
        "B": "SAP MM (Materials Management)",
        "C": "SAP PM (Plant Maintenance)",
        "D": "SAP HR (Human Resources)",
        "E": "SAP QM (Quality Management)",
    },
    "gabarito": "B",
    "explicacao_detalhada": (
        "**Alternativa B (Correta):** O módulo **SAP MM (Materials"
        " Management)** administra o fluxo de compras e estoque e se integra ao"
        " **SAP FI (Financial Accounting)**."
    ),
}


# ----------------------------------------------------
# 3. FUNÇÕES DE SUPABASE E IA (GROQ)
# ----------------------------------------------------
def carregar_historico():
  if not supabase:
    return pd.DataFrame()
  try:
    res = supabase.table("questoes").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()
  except Exception:
    return pd.DataFrame()


def salvar_resposta(q, resposta, acertou, cargo_sel):
  if not supabase:
    return
  cargo_real = q.get("cargo") or cargo_sel
  if "Ciclo Automático" in str(cargo_real):
    cargo_real = "Dataprev - Analista de TI"

  linha = {
      "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "concurso": str(q.get("concurso", "")),
      "cargo": str(cargo_real),
      "banca": str(q.get("banca", "")),
      "materia": str(q.get("materia", "")),
      "enunciado": str(q.get("enunciado", "")),
      "gabarito": str(q.get("gabarito", "")),
      "resposta_usuario": str(resposta),
      "acertou": int(acertou),
  }
  try:
    supabase.table("questoes").insert(linha).execute()
  except Exception:
    pass


def chamar_ia(prompt, json_mode=False):
  if not GROQ_KEY:
    return None

  headers = {
      "Authorization": f"Bearer {GROQ_KEY}",
      "Content-Type": "application/json",
  }
  payload = {
      "model": "llama-3.1-8b-instant",
      "messages": [
          {
              "role": "system",
              "content": (
                  "Você é um tutor especialista em concursos públicos no"
                  " Brasil. Responda EXCLUSIVAMENTE em Português do Brasil."
              ),
          },
          {"role": "user", "content": prompt},
      ],
      "temperature": 0.3,
  }
  if json_mode:
    payload["response_format"] = {"type": "json_object"}

  try:
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=20,
    )
    if res.status_code == 200:
      return res.json()["choices"][0]["message"]["content"]
  except Exception:
    pass
  return None


def processar_json(texto):
  if not texto:
    return QUESTAO_FALLBACK
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
    i1, i2 = t.find("{"), t.rfind("}") + 1
    if i1 != -1 and i2 > i1:
      try:
        return json.loads(t[i1:i2])
      except Exception:
        pass
    return QUESTAO_FALLBACK


def criar_questao(cargo_sel, pedido=""):
  alvo = (
      "Dataprev - Analista de TI"
      if cargo_sel == "Ciclo Automático (Todos os Cargos)"
      else cargo_sel
  )
  info = CARGOS_INFO[alvo]

  # Seleção adaptativa da matéria mais fraca baseada no histórico
  df = carregar_historico()
  materia_foco = None
  if not df.empty and "cargo" in df.columns and "acertou" in df.columns:
    df_c = df[df["cargo"] == alvo]
    if not df_c.empty:
      desempenho = df_c.groupby("materia")["acertou"].mean().reset_index()
      if not desempenho.empty:
        pior = desempenho.sort_values(by="acertou", ascending=True).iloc[0]
        if pior["acertou"] < 0.75:
          materia_foco = pior["materia"]

  if not materia_foco:
    import random

    materia_foco = random.choice(info["materias"])

  prompt = (
      f"Crie uma questão de concurso inédita para o concurso {info['concurso']},"
      f" cargo {alvo}, banca {info['banca']}.\nMatéria obrigatória:"
      f" {materia_foco}.\nInstrução extra: {pedido}\n\nREGRAS:\n1. Escreva"
      " siglas por extenso entre parênteses.\n2. No campo"
      " 'explicacao_detalhada', comente a alternativa correta e o erro de cada"
      ' uma das incorretas.\n\nRetorne JSON puro:\n{\n  "concurso":'
      f' "{info["concurso"]}",\n  "cargo": "{alvo}",\n  "banca":'
      f' "{info["banca"]}",\n  "materia": "{materia_foco}",\n  "assunto":'
      ' "Tópico",\n  "enunciado": "Texto da questão",\n  "opcoes": {"A": "...",'
      ' "B": "...", "C": "...", "D": "...", "E": "..."},\n  "gabarito": "A",\n '
      ' "explicacao_detalhada": "Análise completa em português."\n}'
  )

  res = chamar_ia(prompt, json_mode=True)
  return processar_json(res) if res else QUESTAO_FALLBACK


def criar_aula(q):
  prompt = (
      f"Elabore uma aula teórica completa em Markdown para o cargo"
      f" {q.get('cargo')} na banca {q.get('banca')}.\nMatéria: {q.get('materia')}"
      f" - Assunto: {q.get('assunto')}\nEnunciado: {q.get('enunciado')}\nGabarito"
      f" Oficial: {q.get('gabarito')}\n\nEstruture com: ## 🏛️ 1. Fundamentação"
      " Teórica Completa\n## 🔍 2. Análise Detalhada de Cada Alternativa\n## ⚡"
      f" 3. O Padrão da Banca ({q.get('banca')}) & Pegadinhas\n## 🧠 4. Resumo"
      " Prático"
  )
  res = chamar_ia(prompt, json_mode=False)
  return (
      res
      if res
      else "Não foi possível carregar a aula detalhada no momento."
  )


# ----------------------------------------------------
# 4. INTERFACE DO USUÁRIO
# ----------------------------------------------------
st.sidebar.title("📚 Menu")
menu = st.sidebar.radio(
    "Ir para:", ["📝 Treino de Questões", "📊 Raio-X & Desempenho"]
)
st.sidebar.markdown("---")

cargo_selecionado = st.sidebar.selectbox(
    "🎯 Foco Atual:",
    ["Ciclo Automático (Todos os Cargos)"] + list(CARGOS_INFO.keys()),
)
pedido_usuario = st.sidebar.text_area(
    "💬 Pedido Específico:", placeholder="Ex: Questões fáceis de SQL / Crase"
)

if st.sidebar.button("🔄 Gerar Nova Questão", use_container_width=True):
  for k in defaults.keys():
    st.session_state[k] = None
  st.rerun()

# --- ABA 1: TREINO ---
if menu == "📝 Treino de Questões":
  st.title("🎯 Treino de Questões Adaptativo")

  if st.session_state.cargo_memoria != cargo_selecionado:
    st.session_state.cargo_memoria = cargo_selecionado
    st.session_state.questao_atual = None

  if st.session_state.questao_atual is None:
    with st.spinner("Gerando questão direcionada pelo seu desempenho..."):
      st.session_state.questao_atual = criar_questao(
          cargo_selecionado, pedido_usuario
      )
      st.session_state.status_resposta = None
      st.session_state.escolha = None
      st.session_state.aula_gerada = None

  q = st.session_state.questao_atual
  st.info(
      f"📌 **Cargo:** {q.get('cargo')} | **Banca:** {q.get('banca')} |"
      f" **Matéria:** {q.get('materia')} — *{q.get('assunto')}*"
  )
  st.markdown(f"### {q.get('enunciado')}")

  travado = st.session_state.status_resposta is not None
  opcoes = q.get("opcoes", {})

  escolha = st.radio(
      "Selecione uma resposta:",
      list(opcoes.keys()),
      format_func=lambda k: f"{k}) {opcoes[k]}",
      disabled=travado,
  )

  col1, col2 = st.columns(2)
  if not travado:
    with col1:
      if st.button(
          "✅ Confirmar Resposta", type="primary", use_container_width=True
      ):
        st.session_state.escolha = escolha
        acertou = 1 if escolha == q.get("gabarito") else 0
        st.session_state.status_resposta = (
            "acertou" if acertou == 1 else "errou"
        )
        salvar_resposta(q, escolha, acertou, cargo_selecionado)
        st.rerun()
    with col2:
      if st.button(
          "🤷 Não sei o assunto (Aula Completa)",
          type="secondary",
          use_container_width=True,
      ):
        st.session_state.escolha = "NÃO SEI"
        st.session_state.status_resposta = "nao_sei"
        salvar_resposta(q, "NÃO SEI", 0, cargo_selecionado)
        st.rerun()

  if travado:
    st.markdown("---")
    exp = q.get("explicacao_detalhada", "")
    gab = q.get("gabarito")

    if st.session_state.status_resposta in ["acertou", "errou"]:
      if st.session_state.status_resposta == "acertou":
        st.success(f"🎉 **Acertou!** Gabarito oficial: **{gab}**.")
      else:
        st.error(
            f"❌ **Errou.** Você marcou **{st.session_state.escolha}**, mas o"
            f" gabarito é **{gab}**."
        )
      st.markdown("### 📝 Comentário Detalhado:")
      st.markdown(exp if exp else "Comentário indisponível.")
    elif st.session_state.status_resposta == "nao_sei":
      st.warning(f"💡 **Aula Teórica Completa!** Gabarito oficial: **{gab}**.")
      if st.session_state.aula_gerada is None:
        with st.spinner("Construindo aula detalhada..."):
          st.session_state.aula_gerada = criar_aula(q)
      st.markdown(st.session_state.aula_gerada)

    st.markdown("---")
    if st.button("Próxima Questão ➡️", type="primary", use_container_width=True):
      for k in defaults.keys():
        st.session_state[k] = None
      st.rerun()

# --- ABA 2: RAIO-X ---
elif menu == "📊 Raio-X & Desempenho":
  st.title("📊 Raio-X Completo do Edital")
  df = carregar_historico()

  tot = len(df)
  ac = int(df["acertou"].sum()) if not df.empty and "acertou" in df.columns else 0
  tx_geral = (ac / tot * 100) if tot > 0 else 0

  c1, c2, c3 = st.columns(3)
  c1.metric("Questões Feitas", f"{tot}")
  c2.metric("Acertos", f"{ac}")
  c3.metric("Aproveitamento Geral", f"{tx_geral:.1f}%")

  st.markdown("---")
  tab1, tab2, tab3 = st.tabs([
      "🏢 Dataprev (TI)",
      "🛢️ Transpetro (SAP)",
      "⚙️ Transpetro (Mecânico)",
  ])


  def render_raio_x(cargo_nome):
    st.markdown(f"### 🎯 Desempenho: {cargo_nome}")
    materias = CARGOS_INFO[cargo_nome]["materias"]
    df_c = (
        df[df["cargo"] == cargo_nome]
        if not df.empty and "cargo" in df.columns
        else pd.DataFrame()
    )

    linhas = []
    for m in materias:
      if not df_c.empty and "materia" in df_c.columns:
        sub = df_c[df_c["materia"] == m]
        t_m = len(sub)
        a_m = int(sub["acertou"].sum()) if t_m > 0 else 0
        p_m = (a_m / t_m * 100) if t_m > 0 else 0
      else:
        t_m, a_m, p_m = 0, 0, 0.0

      if t_m == 0:
        status = "⚪ Não Iniciado"
      elif p_m < 60:
        status = "🔴 Crítico"
      elif p_m < 80:
        status = "🟡 Em Evolução"
      else:
        status = "🟢 Dominado"

      linhas.append({
          "Matéria": m,
          "Questões": t_m,
          "Acertos": a_m,
          "Aproveitamento": f"{p_m:.1f}%" if t_m > 0 else "-",
          "Status": status,
      })
    st.table(linhas)


  with tab1:
    render_raio_x("Dataprev - Analista de TI")
  with tab2:
    render_raio_x("Transpetro - Analista SAP")
  with tab3:
    render_raio_x("Transpetro - Mecânico de Manutenção")
