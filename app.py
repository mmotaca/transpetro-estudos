import json
import os
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from supabase import Client, create_client

# ----------------------------------------------------
# 1. CONFIGURAÇÕES BÁSICAS
# ----------------------------------------------------
st.set_page_config(
    page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide"
)

raw_groq = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
GROQ_API_KEY = raw_groq.strip().strip('"').strip("'") if raw_groq else ""

raw_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_URL = raw_url.strip().strip('"').strip("'") if raw_url else ""

raw_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPABASE_KEY = raw_key.strip().strip('"').strip("'") if raw_key else ""


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
    st.caption("Aviso de sincronizacao: " + str(e))


# ----------------------------------------------------
# 3. MAPEAMENTO DE CARGOS E QUESTÃO PADRÃO
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
# 4. COMUNICAÇÃO ROBUSTA COM A GROQ
# ----------------------------------------------------
def chamar_groq(prompt_texto, quer_json=False):
  if not GROQ_API_KEY:
    return None

  cabecalhos = {
      "Authorization": "Bearer " + GROQ_API_KEY,
      "Content-Type": "application/json",
  }

  modelos = [
      "llama-3.1-8b-instant",
      "llama3-8b-8192",
      "llama3-70b-8192",
      "mixtral-8x7b-32768",
  ]

  for m in modelos:
    corpo = {
        "model": m,
        "messages": [{"role": "user", "content": prompt_texto}],
        "temperature": 0.2,
    }
    if quer_json:
      corpo["response_format"] = {"type": "json_object"}

    try:
      resposta = requests.post(
          "https://api.groq.com/openai/v1/chat/completions",
          headers=cabecalhos,
          json=corpo,
          timeout=15,
      )
      if resposta.status_code == 200:
        dados = resposta.json()
        return dados["choices"][0]["message"]["content"]
    except Exception:
      continue

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
    i_inicio = t.find("{")
    i_fim = t.rfind("}") + 1
    if i_inicio != -1 and i_fim > i_inicio:
      return json.loads(t[i_inicio:i_fim])
    return QUESTAO_FALLBACK


# ----------------------------------------------------
# 5. GERADOR DE QUESTÕES E AULAS
# ----------------------------------------------------
def gerar_questao(cargo_selecionado, pedido_extra=""):
  alvo = (
      cargo_selecionado
      if cargo_selecionado != "Ciclo Automático (Todos os Cargos)"
      else "Dataprev - Analista de TI"
  )
  info = CARGOS_INFO.get(alvo, CARGOS_INFO["Dataprev - Analista de TI"])

  linhas_prompt = [
      "Atue como Diretor Virtual de Estudos Especialista em Concursos"
      " Públicos.",
      "Concurso: " + str(info["concurso"]),
      "Cargo: " + str(alvo),
      "Banca: " + str(info["banca"]),
      "Ementa: " + str(info["materias"]),
      "Pedido Extra do Aluno: " + str(pedido_extra),
      "",
      "DIRETRIZES OBRIGATORIAS:",
      (
          "1. SIGLAS: SEMPRE escreva o significado COMPLETO por extenso entre"
          " parenteses ao lado de qualquer sigla tecnica."
      ),
      (
          "2. COMENTARIO DO GABARITO (campo explicacao_detalhada): Explique por"
          " que a correta esta certa e analise cada uma das alternativas"
          " incorretas individualmente mostrando o erro de cada uma."
      ),
      "",
      "Retorne APENAS um JSON valido com este formato exato:",
      "{",
      '  "concurso": "' + str(info["concurso"]) + '",',
      '  "cargo": "' + str(alvo) + '",',
      '  "banca": "' + str(info["banca"]) + '",',
      '  "materia": "Nome da Materia",',
      '  "assunto": "Topico Especifico",',
      '  "enunciado": "Texto claro da questao",',
      (
          '  "opcoes": {"A": "Texto A", "B": "Texto B", "C": "Texto C", "D":'
          ' "Texto D", "E": "Texto E"},'
      ),
      '  "gabarito": "A",',
      (
          '  "explicacao_detalhada": "Analise da correta e de todas as'
          ' incorretas com siglas por extenso entre parenteses."'
      ),
      "}",
  ]

  prompt_final = "\n".join(linhas_prompt)
  resultado = chamar_groq(prompt_final, quer_json=True)
  return limpar_json(resultado) if resultado else QUESTAO_FALLBACK


def gerar_aula(q):
  linhas_aula = [
      (
          "Professor titular preparando candidato para o cargo "
          + str(q.get("cargo", ""))
          + " na banca "
          + str(q.get("banca", ""))
          + "."
      ),
      "O aluno marcou Nao Sei no assunto:",
      "Materia: " + str(q.get("materia", "")),
      "Assunto: " + str(q.get("assunto", "")),
      "Enunciado: " + str(q.get("enunciado", "")),
      "Alternativas: " + json.dumps(q.get("opcoes", {}), ensure_ascii=False),
      "Gabarito Oficial: " + str(q.get("gabarito", "")),
      "",
      "REGRA: Escreva todas as siglas por extenso entre parenteses.",
      "",
      "Estruture a aula completa em Markdown com as secoes:",
      "## 🏛️ 1. Fundamentacao Teorica Completa",
      "## 🔍 2. Analise Detalhada de Cada Alternativa",
      (
          "## ⚡ 3. O Padrao da Banca ("
          + str(q.get("banca", ""))
          + ") & Pegadinhas"
      ),
      "## 🧠 4. Resumo Pratico & Regra de Ouro / Mnemonico",
  ]
  prompt_aula = "\n".join(linhas_aula)
  resultado = chamar_groq(prompt_aula, quer_json=False)
  return (
      resultado
      if resultado
      else "Nao foi possivel carregar a aula detalhada no momento."
  )


# ----------------------------------------------------
# 6. INTERFACE VISUAL DO STREAMLIT
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
    placeholder="Ex: Questão de Crase FGV / Bombas Industriais",
)

if st.sidebar.button("🔄 Gerar Nova Questão", use_container_width=True):
  st.session_state.questao_
