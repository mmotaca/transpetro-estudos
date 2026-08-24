import streamlit as st
import pandas as pd
import requests
import json
import os
from datetime import datetime, date
from supabase import create_client, Client

# ----------------------------------------------------
# 1. CONFIGURAÇÕES
# ----------------------------------------------------
st.set_page_config(page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide")

raw_groq_key = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
GROQ_API_KEY = raw_groq_key.strip().strip('"').strip("'") if raw_groq_key else ""

raw_supa_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_URL = raw_supa_url.strip().strip('"').strip("'") if raw_supa_url else ""

raw_supa_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
SUPABASE_KEY = raw_supa_key.strip().strip('"').strip("'") if raw_supa_key else ""

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
        "acertou": int(acertou)
    }
    try:
        supabase.table("questoes").insert(linha).execute()
    except Exception as e:
        st.caption("Aviso de sincronização: " + str(e))

# ----------------------------------------------------
# 3. CARGOS
# ----------------------------------------------------
CARGOS_INFO = {
    "Dataprev - Analista de TI": {
        "concurso": "Dataprev",
        "banca": "FGV",
        "materias": "Banco de Dados, Governança de TI (COBIT/ITIL), Engenharia de Software, Segurança da Informação, Raciocínio Lógico e Português."
    },
    "Transpetro - Analista SAP": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": "Módulos SAP (ECC/S4HANA, MM, PM, FI, CO, ABAP), Integração de Sistemas, Governança de TI, Raciocínio Lógico e Português."
    },
    "Transpetro - Mecânico de Manutenção": {
        "concurso": "Transpetro",
        "banca": "Cesgranrio",
        "materias": "Mecânica dos Fluidos, Bombas e Compressores, Manutenção Preditiva/Preventiva, Soldagem, Ensaios Não Destrutivos, Metrologia, Elementos de Máquinas, Desenho Técnico, Raciocínio Lógico e Português."
    }
}

QUESTAO_FALLBACK = {
    "concurso": "Transpetro",
    "cargo": "Transpetro - Analista SAP",
    "banca": "Cesgranrio",
    "materia": "Módulos SAP",
    "assunto": "Integração MM e FI",
    "enunciado": "No sistema SAP ECC (Enterprise Core Component), qual módulo principal é responsável pela gestão de compras e suprimentos e se integra ao módulo FI (Financial Accounting) no recebimento de faturas?",
    "opcoes": {
        "A": "SAP SD (Sales and Distribution)",
        "B": "SAP MM (Materials Management)",
        "C": "SAP PM (Plant Maintenance)",
        "D": "SAP HR (Human Resources)",
        "E": "SAP QM (Quality Management)"
    },
    "gabarito": "B",
    "explicacao_detalhada": "**Alternativa B (Correta):** O módulo **SAP MM (Materials Management)** administra o fluxo de suprimentos, compras e inventário. Na entrada da fatura (transação MIRO), gera automaticamente os lançamentos contábeis no módulo **SAP FI (Financial Accounting)**.\n\n- **A (Incorreta):** **SAP SD (Sales and Distribution)** gerencia vendas e entregas.\n- **C (Incorreta):** **SAP PM (Plant Maintenance)** planeja manutenção de ativos.\n- **D (Incorreta):** **SAP HR (Human Resources)** cuida de recursos humanos e folha.\n- **E (Incorreta):** **SAP QM (Quality Management)** gerencia qualidade e testes."
}

# ----------------------------------------------------
# 4. REQUISIÇÃO DIRETA GROQ (ROTAÇÃO ROBUSTA)
# ----------------------------------------------------
def chamar_groq(prompt, formato_json=False):
    if not GROQ_API_KEY:
        return None

    headers = {
        "Authorization": "Bearer " + GROQ_API_KEY,
        "Content-Type": "application/json"
    }
    
    modelos_tentativa = [
        "llama-3.1-8b-instant",
        "llama3-8b-8192",
        "llama3-70b-8192",
        "mixtral-8x7b-32768"
    ]
    
    for mod in modelos_tentativa:
        payload = {
            "model": mod,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        if formato_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=15
            )
            if resp.status_code == 200:
                dados = resp.json()
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
        i1 = t.find("{")
        i2 = t.rfind("}") + 1
        if i1 != -1 and i2 > i1:
            return json.loads(t[i1:i2])
        return QUESTAO_FALLBACK

# ----------------------------------------------------
# 5. GERADORES
# ----------------------------------------------------
def gerar_questao(cargo_selecionado, pedido_extra=""):
    alvo = cargo_selecionado if cargo_selecionado != "Ciclo Automático (Todos os Cargos)" else "Dataprev - Analista de TI"
    info = CARGOS_INFO.get(alvo, CARGOS_INFO["Dataprev - Analista de TI"])
    extra = ("\nPedido do aluno: " + pedido_extra.strip()) if pedido_extra.strip() else ""

    prompt = (
        "Atue como Diretor Virtual de Estudos Especialista em Concursos Públicos.\n"
        "Concurso: " + str(info['concurso']) + "\n"
        "Cargo: " + str(alvo) + "\n"
        "Banca: " + str(info['banca']) + "\n"
        "Ementa: " + str(info['materias']) + "\n"
        + extra + "\n\n"
        "DIRETRIZES OBRIGATÓRIAS:\n"
        "1. SIGLAS: SEMPRE escreva o significado COMPLETO por extenso entre parênteses ao lado de qualquer sigla técnica.\n"
        "2. COMENTÁRIO DO GABARITO (campo 'explicacao_det
