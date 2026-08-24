import streamlit as st
import pandas as pd
import json
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
    st.error("🔑 Chave GEMINI_API_KEY não configurada no Secrets do Streamlit!")
    st.stop()

# Configuração do cliente Gemini
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
# 2. OPERAÇÕES NO BANCO DE DADOS
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
        st.warning(f"Não foi possível salvar no banco: {e}")

# ----------------------------------------------------
# 3. MAPEAMENTO DOS 3 CONCURSOS E CARGOS
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
# 4. PARSER E LIMPEZA DE JSON
# ----------------------------------------------------
def extrair_json_puro(texto):
    texto_limpo = texto.strip()
    if texto_limpo.startswith("```json"):
        texto_limpo = texto_limpo[7:]
    elif texto_limpo.startswith("```"):
        texto_limpo = texto_limpo[3:]
    if texto_limpo.endswith("```"):
        texto_limpo = texto_limpo[:-3]
    texto_limpo = texto_limpo.strip()
    
    try:
        return json.loads(texto_limpo)
    except Exception:
        inicio = texto_limpo.find("{")
        fim = texto_limpo.rfind("}") + 1
        if inicio != -1 and fim > inicio:
            return json.loads(texto_limpo[inicio:fim])
        raise ValueError("JSON retornado inválido.")

# ----------------------------------------------------
# 5. GERADOR DE QUESTÕES
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
                contexto_fraqueza = f"Foco no cargo {cargo_alvo}, matéria {pior['materia']}"
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
                contexto_fraqueza = f"Foco no cargo {cargo_alvo}: matéria {pior['materia']}"

    info = CARGOS_INFO[cargo_alvo]

    instrucao_extra = ""
    if pedido_personalizado and pedido_personalizado.strip():
        instrucao_extra = f"\n⚠️ PEDIDO DO ALUNO: '{pedido_personalizado.strip()}'. Cumpra essa prioridade."

    prompt_instrucao = (
        "Atue como Diretor Virtual de Estudos Especialista em Concursos Públicos.\n"
        f"Concurso: {info['concurso']}\n"
        f"Cargo: {cargo_alvo}\n"
        f"Banca: {info['banca']}\n"
        f"Ementa: {info['materias']}\n"
        f"Status: {contexto_fraqueza}\n"
        f"{instrucao_extra}\n\n"
        "DIRETRIZES OBRIGATÓRIAS:\n"
        "1. SIGLAS: SEMPRE que citar qualquer sigla técnica, escreva o significado COMPLETO entre parênteses logo ao lado.\n"
        "2. COMENTÁRIO DO GABARITO (campo 'explicacao_detalhada'): Explique detalhadamente por que a correta está certa e analise cada uma das alternativas incorretas individualmente, mostrando o erro específico de cada uma.\n\n"
        "Gere UMA questão inédita no formato JSON:\n"
        "{\n"
        f'  "concurso": "{info["concurso"]}",\n'
        f'  "cargo": "{cargo_alvo}",\n'
        f'  "banca": "{info["banca"]}",\n'
        '  "materia": "Nome da Matéria",\n'
        '  "assunto": "Tópico Específico",\n'
        '  "enunciado": "Texto claro da questão",\n'
        '  "opcoes": {"A": "Opção A", "B": "Opção B", "C": "Opção C", "D": "Opção D", "E": "Opção E"},\n'
        '  "gabarito": "A, B, C, D ou E",\n'
        '  "explicacao_detalhada": "Análise da alternativa correta e de cada uma das incorretas com siglas por extenso entre parênteses."\n'
        "}"
    )
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash", generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt_instrucao)
        return extrair_json_puro(response.text)
    except Exception as e:
        st.error(f"Erro na geração da questão: {e}")
        st.stop()

# ----------------------------------------------------
# 6. GERADOR DE AULA COMPLETA
# ----------------------------------------------------
def gerar_aula_profunda(q):
    prompt_aula = (
        f"Você é um professor renomado preparando um candidato para a banca {q['banca']} no cargo {q.get('cargo', q['concurso'])}.\n"
        f"O aluno solicitou a aula completa no assunto:\n"
        f"- Matéria: {q['materia']}\n"
        f"- Assunto: {q.get('assunto', '')}\n"
        f"- Enunciado: {q['enunciado']}\n"
        f"- Alternativas: {json.dumps(q['opcoes'], ensure_ascii=False)}\n"
        f"- Gabarito: {q['gabarito']}\n\n"
        "REGRA: SEMPRE que usar qualquer sigla técnica, escreva o significado COMPLETO entre parênteses.\n\n"
        "Escreva uma AULA COMPLETA em Markdown com:\n"
        "## 🏛️ 1. Fundamentação Teórica Completa\n"
        "## 🔍 2. Análise Detalhada de Cada Alternativa\n"
        f"## ⚡ 3. O Padrão da Banca ({q['banca']}) & Pegadinhas\n"
        "## 🧠 4. Resumo Prático & Mnemônico / Regra de Ouro\n"
    )

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt_aula)
        return response.text
    except Exception as e:
        return f"Não foi possível carregar a aula detalhada: {e}"

# ----------------------------------------------------
# 7. ESTRUTURA PRINCIPAL & NAVEGAÇÃO
# ----------------------------------------------------
st.set_page_config(page_title="Tutor Concursos Pro", page_icon="🎯", layout="wide")

st.sidebar.title("📚 Central de Estudos")
menu = st.sidebar.radio("Navegar:", ["📝 Treino de Questões", "📊 Dashboard Geral & Por Cargo"])

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Foco de Estudo Atual:")
cargo_selecionado = st.sidebar.selectbox(
    "Escolha o Cargo:",
    ["Ciclo Automático (Todos os Cargos)"] + list(CARGOS_
