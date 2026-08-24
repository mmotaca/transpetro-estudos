import json
import os
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
from supabase import Client, create_client

# ----------------------------------------------------
# 1. CONFIGURAÇÕES & INICIALIZAÇÃO SEGURA DO ESTADO
# ----------------------------------------------------
st.set_page_config(
    page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide"
)

# Inicialização de memória
for chave in [
    "questao_atual",
    "status_resposta",
    "escolha",
    "aula_gerada",
    "cargo_memoria",
]:
  if chave not in st.session_state:
    st.session_state[chave] = None

raw_groq = st.secrets.get(
    "GROQ_API_KEY",
    st.secrets.get("groq_api_key", os.environ.get("GROQ_API_KEY", "")),
)
GROQ_API_KEY = str(raw_groq).strip().strip('"').strip("'") if raw_groq else ""

raw_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_URL = str(raw_url).strip().strip('"').strip("'") if raw_url else ""

raw_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPABASE_KEY = str(raw_key).strip().strip('"').strip("'") if raw_key else ""


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
# 2. OPERAÇÕES NO BANCO DE DADOS
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
    st.caption("Aviso de sincronização: " + str(e))


# ----------------------------------------------------
# 3. MAPEAMENTO DE CARGOS & QUESTÃO PADRÃO
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
# 4. REQUISIÇÃO DIRETA COM DIAGNÓSTICO
# ----------------------------------------------------
def chamar_groq(prompt_texto, quer_json=False):
  if not GROQ_API_KEY:
    st.error(
        "🔑 Chave `GROQ_API_KEY` não encontrada nas configurações de Secrets!"
    )
    return None

  cabecalhos = {
      "Authorization": "Bearer " + GROQ_API_KEY,
      "Content-Type": "application/json",
  }

  modelos = [
      "llama-3.1-8b-instant",
      "llama3-8b-8192",
      "gemma2-9b-it",
      "mixtral-8x7b-32768",
  ]

  erros = []

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
          timeout=20,
      )
      if resposta.status_code == 200:
        dados = resposta.json()
        return dados["choices"][0]["message"]["content"]
      else:
        erros.append(f"{m} (HTTP {resposta.status_code}): {resposta.text}")
    except Exception as e:
      erros.append(f"{m} (Erro de Conexão): {e}")

  st.error("❌ Falha na conexão com a IA Groq:\n" + "\n".join(erros))
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
      try:
        return json.loads(t[i_inicio:i_fim])
      except Exception:
        pass
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
  extra = (
      ("\nPedido prioritário: " + pedido_extra.strip())
      if pedido_extra.strip()
      else ""
  )

  prompt = (
      "Atue como Diretor Virtual de Estudos Especialista em Concursos"
      " Públicos.\nConcurso: "
      + str(info["concurso"])
      + "\nCargo: "
      + str(alvo)
      + "\nBanca: "
      + str(info["banca"])
      + "\nEmenta: "
      + str(info["materias"])
      + extra
      + "\n\nDIRETRIZES OBRIGATÓRIAS:\n1. SIGLAS: SEMPRE escreva o significado"
      " COMPLETO por extenso entre parênteses ao lado de qualquer sigla"
      " técnica.\n2. COMENTÁRIO DO GABARITO (campo 'explicacao_detalhada'):"
      " Explique detalhadamente por que a alternativa correta está certa e"
      " analise cada uma das alternativas incorretas individualmente, mostrando"
      " o erro específico de cada uma.\n\nRetorne ESTRITAMENTE em formato"
      ' JSON:\n{\n  "concurso": "'
      + str(info["concurso"])
      + '",\n  "cargo": "'
      + str(alvo)
      + '",\n  "banca": "'
      + str(info["banca"])
      + '",\n  "materia": "Nome da Matéria",\n  "assunto": "Tópico'
      ' Específico",\n  "enunciado": "Texto da questão",\n  "opcoes": {"A":'
      ' "Texto A", "B": "Texto B", "C": "Texto C", "D": "Texto D", "E": "Texto'
      ' E"},\n  "gabarito": "A",\n  "explicacao_detalhada": "Análise da'
      " alternativa correta e de cada uma das incorretas com siglas por extenso"
      ' entre parênteses."\n}'
  )

  resposta = chamar_groq(prompt, quer_json=True)
  return limpar_json(resposta) if resposta else QUESTAO_FALLBACK


def gerar_aula(q):
  prompt = (
      "Professor titular preparando candidato para a banca "
      + str(q.get("banca", ""))
      + " no cargo "
      + str(q.get("cargo", q.get("concurso", "")))
      + ".\nO aluno marcou 'Não Sei' no assunto:\nMatéria: "
      + str(q.get("materia", ""))
      + " | Assunto: "
      + str(q.get("assunto", ""))
      + "\nEnunciado: "
      + str(q.get("enunciado", ""))
      + "\nAlternativas: "
      + json.dumps(q.get("opcoes", {}), ensure_ascii=False)
      + "\nGabarito Oficial: "
      + str(q.get("gabarito", ""))
      + "\n\nREGRA: Escreva todas as siglas por extenso entre"
      " parênteses.\n\nEstruture a aula completa em Markdown com:\n## 🏛️ 1."
      " Fundamentação Teórica Completa\n## 🔍 2. Análise Detalhada de Cada"
      " Alternativa\n## ⚡ 3. O Padrão da Banca ("
      + str(q.get("banca", ""))
      + ") & Pegadinhas\n## 🧠 4. Resumo Prático & Regra de Ouro / Mnemônico\n"
  )
  resposta = chamar_groq(prompt, quer_json=False)
  return (
      resposta
      if resposta
      else "Não foi possível carregar a aula detalhada no momento."
  )


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
    placeholder="Ex: Questão de Crase FGV / Bombas Industriais",
)

if st.sidebar.button("🔄 Gerar Nova Questão", use_container_width=True):
  st.session_state.questao_atual = None
  st.session_state.status_resposta = None
  st.session_state.escolha = None
  st.session_state.aula_gerada = None
  st.rerun()

# --- ABA 1: TREINO DE QUESTÕES ---
if menu == "📝 Treino de Questões":
  st.title("🎯 Treino de Questões Adaptativo")

  if st.session_state.cargo_memoria != cargo_selecionado:
    st.session_state.cargo_memoria = cargo_selecionado
    st.session_state.questao_atual = None

  if st.session_state.questao_atual is None:
    with st.spinner("Carregando questão inédita na Groq..."):
      st.session_state.questao_atual = gerar_questao(
          cargo_selecionado, pedido_usuario
      )
      st.session_state.status_resposta = None
      st.session_state.escolha = None
      st.session_state.aula_gerada = None

  q = st.session_state.questao_atual

  st.info(
      "📌 **Cargo:** "
      + str(q.get("cargo", q
