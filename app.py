from datetime import date, datetime
import json
import os
import pandas as pd
import requests
import streamlit as st
from supabase import Client, create_client

# ----------------------------------------------------
# 1. CONFIGURAÇÕES (GROQ + SUPABASE)
# ----------------------------------------------------
raw_groq_key = st.secrets.get(
    "GROQ_API_KEY", os.environ.get("GROQ_API_KEY", "")
)
GROQ_API_KEY = (
    raw_groq_key.strip().strip('"').strip("'") if raw_groq_key else ""
)

raw_supa_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_URL = (
    raw_supa_url.strip().strip('"').strip("'") if raw_supa_url else ""
)

raw_supa_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPABASE_KEY = (
    raw_supa_key.strip().strip('"').strip("'") if raw_supa_key else ""
)

if not GROQ_API_KEY:
  st.error("🔑 Configure a chave GROQ_API_KEY no Secrets do Streamlit!")
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
    st.warning(f"Aviso ao salvar histórico: {e}")


# ----------------------------------------------------
# 3. MAPEAMENTO DOS 3 CARGOS
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
# 4. REQUISIÇÃO DIRETA AO GROQ (LLAMA 3.3 70B)
# ----------------------------------------------------
def chamar_groq(prompt, formato_json=False):
  headers = {
      "Authorization": f"Bearer {GROQ_API_KEY}",
      "Content-Type": "application/json",
  }
  payload = {
      "model": "llama-3.3-70b-versatile",
      "messages": [{"role": "user", "content": prompt}],
      "temperature": 0.2,
  }

  if formato_json:
    payload["response_format"] = {"type": "json_object"}

  try:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=25,
    )
    if resp.status_code == 200:
      return resp.json()["choices"][0]["message"]["content"]
    else:
      st.error(f"Erro no Groq (HTTP {resp.status_code}): {resp.text}")
      st.stop()
  except Exception as e:
    st.error(f"Erro de conexão com o Groq: {e}")
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
    raise ValueError("Formato JSON retornado pela IA foi inválido.")


# ----------------------------------------------------
# 5. GERADOR DE QUESTÕES
# ----------------------------------------------------
def gerar_questao(cargo_selecionado, pedido_extra=""):
  df = carregar_dados()
  alvo = (
      cargo_selecionado
      if cargo_selecionado != "Ciclo Automático (Todos os Cargos)"
      else "Dataprev - Analista de TI"
  )
  info = CARGOS_
