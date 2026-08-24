import streamlit as st
import pandas as pd
import json
import re
import os
from datetime import datetime, date, timedelta
from supabase import create_client, Client
import google.generativeai as genai

# ----------------------------------------------------
# 1. CONFIGURAÇÕES SEGURAS (GEMINI + SUPABASE)
# ----------------------------------------------------
raw_gemini_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
GEMINI_API_KEY = raw_gemini_key.strip().strip('"').strip("'") if raw_gemini_key else ""

raw_supa_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_URL = raw_supa_url.strip().strip('"').strip("'") if raw_supa_url else ""

raw_supa_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPABASE_KEY = raw_supa_key.strip().strip('"').strip("'") if raw_supa_key else ""

if not GEMINI_API_KEY:
    st.error("🔑 **Chave GEMINI_API_KEY não configurada!** Acesse Settings > Secrets no Streamlit Cloud.")
    st.stop()

if not GEMINI_API_KEY.startswith("AIza"):
    st.error("⚠️ **Chave do Gemini Inválida!** A chave de API do Google AI Studio precisa começar obrigatoriamente com `AIzaSy...`. Acesse [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) para gerar a sua chave correta.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

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
# 2. BANCO DE DADOS SUPABASE
# ----------------------------------------------------
def carregar_dados():
    if not supabase:
        return pd.DataFrame()
    try:
        response = supabase.table("questoes").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def salvar_resposta_supabase(nova_linha):
    if not supabase:
        return
    try:
        supabase.table("questoes").insert(nova_linha).execute()
    except Exception as e:
        st.warning(f"Não foi possível gravar no banco em nuvem: {e}")

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
# 4. TRATAMENTO E PARSER DE JSON
# ----------------------------------------------------
def extrair_json_puro(texto):
    texto_limpo = re.sub(r"^```json\s*|\s*
