from datetime import datetime
import json
import os
import pandas as pd
import requests
import streamlit as st
from supabase import Client, create_client

# ----------------------------------------------------
# 1. CONFIGURAÇÕES & MEMÓRIA
# ----------------------------------------------------
st.set_page_config(
    page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide"
)

chaves_memoria = [
    "questao_atual",
    "status_resposta",
    "escolha",
    "aula_gerada",
    "cargo_memoria",
]
for k in chaves_memoria:
  if k not in st.session_state:
    st.session_state[k] = None

raw_groq = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
GROQ_KEY = (
    str(raw_groq).strip().strip('"').strip("'")
    if raw_groq is not None
    else ""
)

raw_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPA_URL = str(raw_url).strip().strip('"').strip("'") if raw_url is not None else ""

raw_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPA_KEY = str(raw_key).strip().strip('"').strip("'") if raw_key is not None else ""


@st.cache_resource
def get_supabase():
  if SUPA_URL and SUPA_KEY:
    try:
      return create_client(SUPA_URL, SUPA_KEY)
    except Exception:
      return None
  return None


supabase = get_supabase()


# ----------------------------------------------------
# 2. BANCO DE DADOS
# ----------------------------------------------------
def carregar_dados():
  if not supabase:
    return pd.DataFrame()
  try:
    res = supabase.table("questoes").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()
  except Exception:
    return pd.DataFrame()


def registrar_resposta(q, resposta, acertou, cargo_sel):
  if not supabase:
    return
  cargo_final = q.get("cargo") or cargo_sel
  linha = {
      "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "concurso": str(q.get("concurso", "")),
      "cargo": str(cargo_final),
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
    st.caption("Aviso de sincronização: " + str(e))


# ----------------------------------------------------
# 3. BASE DE CARGOS & QUESTÃO DE RESERVA
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

QUESTAO_FALLBACK = {
    "concurso": "Transpetro",
    "cargo": "Transpetro - Analista SAP",
    "banca": "Cesgranrio",
    "materia": "Módulos SAP",
    "assunto": "Integração MM e FI",
    "enunciado": (
        "No sistema SAP ECC (Enterprise Core Component), qual módulo principal"
        " é responsável pela gestão de compras e estoques e se integra ao"
        " módulo FI (Financial Accounting) no recebimento de faturas?"
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
        " Management)** administra o fluxo de compras e estoque. Na entrada da"
        " fatura, gera os lançamentos no módulo **SAP FI (Financial"
        " Accounting)**.\n\n- **A (Incorreta):** **SAP SD (Sales and"
        " Distribution)** cuida de vendas.\n- **C (Incorreta):** **SAP PM"
        " (Plant Maintenance)** planeja manutenção.\n- **D (Incorreta):** **SAP"
        " HR (Human Resources)** gerencia pessoas.\n- **E (Incorreta):** **SAP"
        " QM (Quality Management)** gerencia qualidade."
    ),
}


# ----------------------------------------------------
# 4. AUTODESCOBERTA DINÂMICA DE MODELOS GROQ
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def obter_modelos_ativos_groq():
  if not GROQ_KEY:
    return ["llama-3.1-8b-instant"]

  cabecalhos = {"Authorization": f"Bearer {GROQ_KEY}"}
  try:
    resp = requests.get(
        "https://api.groq.com/openai/v1/models", headers=cabecalhos, timeout=10
    )
    if resp.status_code == 200:
      dados = resp.json()
      ids_disponiveis = [m["id"] for m in dados.get("data", [])]

      # Filtra apenas modelos de texto suportados e remove descontinuados
      modelos_chat = [
          m
          for m in ids_disponiveis
          if not any(
              sub in m
              for sub in [
                  "whisper",
                  "guard",
                  "embed",
                  "vision",
                  "safeguard",
                  "gemma2",
                  "llama3-",
              ]
          )
      ]

      preferencias = [
          "llama-3.1-8b-instant",
          "llama-3.3-70b-versatile",
          "llama-3.2-3b-preview",
          "llama-3.2-1b-preview",
          "qwen-2.5-32b",
      ]
      ordenados = [p for p in preferencias if p in modelos_chat]
      for m in modelos_chat:
        if m not in ordenados:
          ordenados.append(m)

      if ordenados:
        return ordenados
  except Exception:
    pass

  return ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]


def chamar_groq(prompt_texto, quer_json=False):
  if not GROQ_KEY:
    st.error("🔑 Configure a chave GROQ_API_KEY no Secrets do Streamlit!")
    return None

  cabecalhos = {
      "Authorization": f"Bearer {GROQ_KEY}",
      "Content-Type": "application/json",
  }

  modelos = obter_modelos_ativos_groq()
  erros_log = []

  for m in modelos:
    corpo = {
        "model": m,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é um tutor especialista em concursos públicos"
                    " brasileiros."
                ),
            },
            {"role": "user", "content": prompt_texto},
        ],
        "temperature": 0.2,
    }
    if quer_json:
      corpo["response_format"] = {"type": "json_object"}

    try:
      res = requests.post(
          "https://api.groq.com/openai/v1/chat/completions",
          headers=cabecalhos,
          json=corpo,
          timeout=20,
      )
      if res.status_code == 200:
        dados = res.json()
        return dados["choices"][0]["message"]["content"]
      else:
        erros_log.append(f"{m} (HTTP {res.status_code}): {res.text}")
    except Exception as e:
      erros_log.append(f"{m} (Conexão): {e}")

  if erros_log:
    st.error(
        "❌ Falha de comunicação com os modelos da Groq:\n\n"
        + "\n\n".join(erros_log)
    )
  return None


def limpar_json(texto):
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
    i_ini = t.find("{")
    i_fim = t.rfind("}") + 1
    if i_ini != -1 and i_fim > i_ini:
      try:
        return json.loads(t[i_ini:i_fim])
      except Exception:
        pass
    return QUESTAO_FALLBACK


# ----------------------------------------------------
# 5. GERADORES DE QUESTÕES E AULAS
# ----------------------------------------------------
def gerar_questao(cargo_sel, pedido_extra=""):
  alvo = (
      "Dataprev - Analista de TI"
      if cargo_sel == "Ciclo Automático (Todos os Cargos)"
      else cargo_sel
  )
  info = CARGOS_INFO.get(alvo, CARGOS_INFO["Dataprev - Analista de TI"])
  ped = str(pedido_extra).strip()

  prompt = (
      "Atue como Diretor Virtual de Estudos Especialista em Concursos"
      f" Públicos.\nConcurso: {info['concurso']}\nCargo: {alvo}\nBanca:"
      f" {info['banca']}\nEmenta: {info['materias']}\nPedido: {ped}\n\nREGRAS"
      " OBRIGATÓRIAS:\n1. Escreva todas as siglas por extenso entre"
      " parênteses.\n2. Explique detalhadamente a alternativa correta e cada"
      ' uma das incorretas.\n\nRetorne ESTRITAMENTE em formato JSON:\n{\n '
      f' "concurso": "{info["concurso"]}",\n  "cargo": "{alvo}",\n  "banca":'
      f' "{info["banca"]}",\n  "materia": "Nome da Matéria",\n  "assunto":'
      ' "Tópico",\n  "enunciado": "Texto da questão",\n  "opcoes": {"A":'
      ' "Texto A", "B": "Texto B", "C": "Texto C", "D": "Texto D", "E": "Texto'
      ' E"},\n  "gabarito": "A",\n  "explicacao_detalhada": "Análise completa'
      ' com siglas por extenso entre parênteses."\n}'
  )

  res = chamar_groq(prompt, quer_json=True)
  return limpar_json(res) if res else QUESTAO_FALLBACK


def gerar_aula(q):
  c_nome = str(q.get("cargo") or q.get("concurso", ""))
  b_nome = str(q.get("banca", ""))
  m_nome = str(q.get("materia", ""))
  a_nome = str(q.get("assunto", ""))
  e_nome = str(q.get("enunciado", ""))
  g_nome = str(q.get("gabarito", ""))
  ops = json.dumps(q.get("opcoes", {}), ensure_ascii=False)

  prompt = (
      f"Professor de concurso preparando aluno para {c_nome} na banca"
      f" {b_nome}.\nO aluno marcou 'Não Sei' no assunto: {m_nome} - {a_nome}\n"
      f"Enunciado: {e_nome}\nAlternativas: {ops}\nGabarito Oficial:"
      f" {g_nome}\n\nEscreva todas as siglas por extenso entre parênteses.\n"
      "Crie uma aula completa em Markdown estruturada com:\n"
      "## 🏛️ 1. Fundamentação Teórica Completa\n"
      "## 🔍 2. Análise Detalhada de Cada Alternativa\n"
      f"## ⚡ 3. O Padrão da Banca ({b_nome}) & Pegadinhas\n"
      "## 🧠 4. Resumo Prático & Regra de Ouro / Mnemônico"
  )

  res = chamar_groq(prompt, quer_json=False)
  return res if res else "Não foi possível carregar a aula detalhada no momento."


# ----------------------------------------------------
# 6. INTERFACE STREAMLIT
# ----------------------------------------------------
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
    placeholder="Ex: Crase FGV / Bombas Industriais",
)

if st.sidebar.button("🔄 Gerar Nova Questão", use_container_width=True):
  st.session_state.questao_atual = None
  st.session_state.status_resposta = None
  st.session_state.escolha = None
  st.session_state.aula_gerada = None
  st.rerun()

if menu == "📝 Treino de Questões":
  st.title("🎯 Treino de Questões Adaptativo")

  if st.session_state.cargo_memoria != cargo_selecionado:
    st.session_state.cargo_memoria = cargo_selecionado
    st.session_state.questao_atual = None

  if st.session_state.questao_atual is None:
    with st.spinner("Carregando questão inédita..."):
      st.session_state.questao_atual = gerar_questao(
          cargo_selecionado, pedido_usuario
      )
      st.session_state.status_resposta = None
      st.session_state.escolha = None
      st.session_state.aula_gerada = None

  q = st.session_state.questao_atual
  c_txt = str(q.get("cargo") or q.get("concurso", ""))
  b_txt = str(q.get("banca", ""))
  m_txt = str(q.get("materia", ""))
  a_txt = str(q.get("assunto", ""))
  e_txt = str(q.get("enunciado", ""))

  st.info(
      f"📌 **Cargo:** {c_txt} | **Banca:** {b_txt} | **Matéria:** {m_txt} —"
      f" *{a_txt}*"
  )
  st.markdown(f"### {e_txt}")

  travado = st.session_state.status_resposta is not None
  opcoes_dict = q.get("opcoes", {})

  escolha = st.radio(
      "Selecione uma resposta:",
      list(opcoes_dict.keys()),
      format_func=lambda k: f"{k}) {opcoes_dict[k]}",
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
        registrar_resposta(q, escolha, acertou, cargo_selecionado)
        st.rerun()
    with col2:
      if st.button(
          "🤷 Não sei o assunto (Aula Completa)",
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
    gab = str(q.get("gabarito", ""))

    if st.session_state.status_resposta == "acertou":
      st.success(f"🎉 **Acertou!** Gabarito oficial: **{gab}**.")
      st.markdown("### 📝 Comentário das Alternativas:")
      st.markdown(exp)
    elif st.session_state.status_resposta == "errou":
      st.error(
          f"❌ **Errou.** Você marcou **{st.session_state.escolha}**, mas o"
          f" gabarito oficial é **{gab}**."
      )
      st.markdown("### 📝 Comentário das Alternativas:")
      st.markdown(exp)
    elif st.session_state.status_resposta == "nao_sei":
      st.warning(f"💡 **Aula Teórica Completa!** Gabarito oficial: **{gab}**.")
      if st.session_state.aula_gerada is None:
        with st.spinner("Construindo aula detalhada..."):
          st.session_state.aula_gerada = gerar_aula(q)
      st.markdown(st.session_state.aula_gerada)

    st.markdown("---")
    if st.button("Próxima Questão ➡️", type="primary", use_container_width=True):
      st.session_state.questao_atual = None
      st.session_state.status_resposta = None
      st.session_state.escolha = None
      st.session_state.aula_gerada = None
      st.rerun()

elif menu == "📊 Painel de Desempenho":
  st.title("📊 Painel de Desempenho dos Concursos")
  df = carregar_dados()
  if df.empty or "acertou" not in df.columns:
    st.info("Nenhuma questão registrada ainda. Comece a praticar no menu!")
  else:
    tot = len(df)
    ac = int(df["acertou"].sum())
    taxa = (ac / tot * 100) if tot > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Resolvido", f"{tot} questões")
    c2.metric("Total de Acertos", f"{ac} acertos")
    c3.metric("Aproveitamento Geral", f"{taxa:.1f}%")

    st.markdown("---")
    st.subheader("🎯 Desempenho por Concurso e Cargo")
    tab1, tab2, tab3 = st.tabs([
        "🏢 Dataprev (TI)",
        "🛢️ Transpetro (SAP)",
        "⚙️ Transpetro (Mecânica)",
    ])

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
      st.caption(f"Meta de questões: {tot_c}/{meta}")

    with tab1:
      mostrar_cargo("Dataprev - Analista de TI", 400)
    with tab2:
      mostrar_cargo("Transpetro - Analista SAP", 350)
    with tab3:
      mostrar_cargo("Transpetro - Mecânico de Manutenção", 350)
