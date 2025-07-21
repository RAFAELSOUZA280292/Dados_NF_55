import streamlit as st
import requests
import pandas as pd
import re
import datetime
import io
import time # Para pausas em caso de erro 429 da API e controle de rate limit
import os   # Para verificar a existência do arquivo de logo
from zoneinfo import ZoneInfo # Para fuso horário de Brasília

# --- Constantes da Aplicação ---
# Define o fuso horário de Brasília para a estimativa de tempo
BRASILIA_TZ = ZoneInfo("America/Sao_Paulo") 
# Limite de requisições por chave para respeitar APIs públicas (4 segundos por chave)
RATE_LIMIT_SECONDS = 4 
# URL da API de consulta CNPJ (open.cnpja.com para regime tributário)
API_CNPJA_URL = "https://open.cnpja.com/office/" 

# --- Configuração da Página ---
st.set_page_config(
    page_title="Dados NF-e - Adapta",
    layout="wide", # Layout 'wide' para melhor visualização da tabela
    initial_sidebar_state="collapsed"
)

# --- Adicionar o Logo ---
# Caminho para o logo. Por padrão, o Streamlit busca caminhos relativos ao diretório do script.
logo_path = "images_2/logo.png" 

if os.path.exists(logo_path):
    st.image(logo_path, width=400) # Ajuste a largura conforme necessário
else:
    st.warning(f"O arquivo de logo não foi encontrado em '{logo_path}'. Verifique o caminho.")

# --- Estilo CSS Personalizado (Adaptado do seu app de Lote) ---
st.markdown(f"""
<style>
    /* Cor de Fundo Principal da Aplicação - Muito Escuro / Quase Preto */
    .stApp {{
        background-color: #1A1A1A; /* Quase preto */
        color: #EEEEEE; /* Cinza claro para o texto principal */
    }}

    /* Títulos (h1 a h6) */
    h1, h2, h3, h4, h5, h6 {{
        color: #FFC300; /* Amarelo Riqueza */
    }}

    /* Estilo dos Labels e Inputs de Texto */
    .stTextInput label, .stTextArea label {{
        color: #FFC300; /* Amarelo Riqueza para os labels */
    }}
    .stTextInput div[data-baseweb="input"] > div, .stTextArea div[data-baseweb="textarea"] > textarea {{
        background-color: #333333; /* Cinza escuro para o fundo do input */
        color: #EEEEEE; /* Cinza claro para o texto digitado */
        border: 1px solid #FFC300; /* Borda Amarelo Riqueza */
    }}
    /* Estilo do input/textarea quando focado */
    .stTextInput div[data-baseweb="input"] > div:focus-within, .stTextArea div[data-baseweb="textarea"] > textarea:focus-within {{
        border-color: #FFD700; /* Amarelo ligeiramente mais claro no foco */
        box-shadow: 0 0 0 0.1rem rgba(255, 195, 0, 0.25); /* Sombra sutil */
    }}

    /* Estilo dos Botões */
    .stButton > button {{
        background-color: #FFC300; /* Amarelo Riqueza */
        color: #1A1A1A; /* Texto escuro no botão amarelo */
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
        font-weight: bold;
        transition: background-color 0.3s ease; /* Transição suave no hover */
    }}
    /* Estilo do botão ao passar o mouse */
    .stButton > button:hover {{
        background-color: #FFD700; /* Amarelo ligeiramente mais claro no hover */
        color: #000000; /* Preto total no texto para contraste */
    }}

    /* Estilo dos Expanders (não usado aqui, mas mantido para consistência se adicionar) */
    .stExpander {{
        background-color: #333333; /* Cinza escuro para o fundo do expander */
        border: 1px solid #FFC300; /* Borda Amarelo Riqueza */
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
    }}
    .stExpander > div > div > div > p {{
        color: #EEEEEE; /* Cinza claro para o título do expander */
    }}

    /* Estilo para st.info, st.warning, st.error */
    .stAlert {{
        background-color: #333333; /* Cinza escuro para o fundo dos alertas */
        color: #EEEEEE; /* Cinza claro para o texto */
        border-left: 5px solid #FFC300; /* Borda esquerda Amarelo Riqueza */
        border-radius: 5px;
    }}
    .stAlert > div > div > div > div > span {{
        color: #EEEEEE !important; /* Garante que o texto dentro do alerta seja claro */
    }}
    .stAlert > div > div > div > div > svg {{
        color: #FFC300 !important; /* Garante que o ícone do alerta seja amarelo */
    }}

    /* Linhas divisórias */
    hr {{
        border-top: 1px solid #444444; /* Cinza para divisórias */
    }}
</style>
""", unsafe_allow_html=True)

st.title("📄 Dados Detalhados de NF-e (Chave de Acesso)")
st.markdown("Cole as chaves de acesso das NF-e para analisar sua composição e o regime tributário do emitente.")

# --- Funções Auxiliares ---

def parse_nfe_key(key):
    """
    Analisa uma chave de acesso de NF-e de 44 dígitos em seus componentes.
    Assume que a chave já foi validada como tendo 44 dígitos e sendo numérica.
    """
    return {
        "UF": key[0:2],
        "Ano/Mês Emissão": key[2:6],
        "CNPJ Emitente": key[6:20],
        "Modelo Doc.": key[20:22],
        "Série": key[22:25],
        "Número NF-e": key[25:34],
        "Tipo Emissão": key[34:35],
        "Código Numérico": key[35:43],
        "Dígito Verificador": key[43:44]
    }

def clean_cnpj(cnpj_text):
    """Remove caracteres não numéricos do CNPJ."""
    return re.sub(r'\D', '', cnpj_text)

def get_cnpj_tax_regime(cnpj):
    """
    Consulta a API open.cnpja.com para detalhes do CNPJ e extrai o regime tributário.
    Implementa um retry básico para erros 429 (muitas requisições).
    """
    clean_cnpj_num = clean_cnpj(cnpj)
    if not clean_cnpj_num.isdigit() or len(clean_cnpj_num) != 14:
        return "CNPJ Inválido"

    url = f"{API_CNPJA_URL}{clean_cnpj_num}"
    try:
        # Adiciona um timeout para evitar que a requisição trave indefinidamente
        response = requests.get(url, timeout=15) 

        if response.status_code == 200:
            data = response.json()
            company = data.get('company', {})
            simples = company.get('simples', {})
            simei = company.get('simei', {})

            simples_optant = simples.get('optant', False)
            simei_optant = simei.get('optant', False)

            # Prioriza SIMEI, pois é um regime mais específico dentro do Simples Nacional
            if simei_optant:
                return "SIMEI"
            elif simples_optant:
                return "Simples Nacional"
            else:
                return "Regime Normal / Outros"
        elif response.status_code == 429:
            # st.warning(f"Muitas requisições para CNPJ {clean_cnpj_num} (Código 429). Tentando novamente em 5 segundos...")
            time.sleep(5) # Pausa por 5 segundos antes de tentar novamente
            return get_cnpj_tax_regime(cnpj) # Tenta novamente (retry simples)
        elif response.status_code == 404:
            return "CNPJ Não Encontrado na API"
        else:
            return f"Erro na API ({response.status_code})"
    except requests.exceptions.Timeout:
        return "Tempo Limite da API Excedido"
    except requests.exceptions.ConnectionError:
        return "Erro de Conexão com a API"
    except Exception as e:
        return f"Erro Inesperado: {e}"

# --- Interface Streamlit ---

st.text_area(
    "Cole as chaves de acesso das NF-e aqui (uma por linha, até 400 chaves):",
    height=250,
    key="nfe_keys_input",
    placeholder="Exemplo:\n51250501624149000538550010001098421003295263\n51250502879190000194550010000663741957724321"
)

if st.button("Processar Chaves de Acesso"):
    keys_input = st.session_state.nfe_keys_input.strip()
    
    if not keys_input:
        st.warning("Por favor, cole as chaves de acesso antes de processar.")
        st.session_state.nfe_results_df = pd.DataFrame() # Limpa resultados anteriores
    else:
        raw_keys = keys_input.split('\n')
        # Filtra linhas vazias e remove espaços em branco
        cleaned_keys = [k.strip() for k in raw_keys if k.strip()]
        
        if len(cleaned_keys) > 400:
            st.error(f"Você colou {len(cleaned_keys)} chaves, mas o limite é de 400. Por favor, reduza a quantidade.")
            st.session_state.nfe_results_df = pd.DataFrame()
        else:
            results = []
            total_keys = len(cleaned_keys)
            start_time = time.time()

            # Placeholders para as mensagens de status e progresso
            progress_bar = st.progress(0, text="Iniciando processamento...")
            time_estimate_text = st.empty()
            current_request_text = st.empty()
            
            st.info(f"""
                **Atenção:** Será feita 1 requisição a cada **{RATE_LIMIT_SECONDS:.0f} segundos** para respeitar os limites de requisição de APIs públicas.
                Para a sua consulta de lote de **{total_keys} chaves**, o tempo estimado de processamento será de
                **{str(datetime.timedelta(seconds=total_keys * RATE_LIMIT_SECONDS))}**.
                Durante o processamento, é importante manter a página ativa no navegador para evitar interrupções.
                """, icon="ℹ️")

            for i, key in enumerate(cleaned_keys):
                # Controle de Rate Limit (pausa antes da próxima requisição)
                if i > 0: # Não pausa antes da primeira requisição
                    elapsed_for_this_loop = time.time() - (start_time + i * RATE_LIMIT_SECONDS)
                    time_to_wait = RATE_LIMIT_SECONDS - elapsed_for_this_loop
                    if time_to_wait > 0:
                        time.sleep(time_to_wait)

                # Atualiza a barra de progresso
                progress = (i + 1) / total_keys
                progress_bar.progress(progress, text=f"Processando chave {i+1} de {total_keys}...")
                
                # Estimativa de tempo
                elapsed_time = time.time() - start_time
                remaining_keys = total_keys - (i + 1)
                
                # Ajusta o tempo por requisição com base no que já passou
                time_per_future_request = max(RATE_LIMIT_SECONDS, elapsed_time / (i + 1) if (i + 1) > 0 else RATE_LIMIT_SECONDS)
                
                estimated_remaining_seconds = remaining_keys * time_per_future_request
                
                current_brasilia_time = datetime.datetime.now(BRASILIA_TZ)
                estimated_finish_time = current_brasilia_time + datetime.timedelta(seconds=estimated_remaining_seconds)
                
                time_estimate_text.info(
                    f"Progresso: **{int(progress*100)}%**\n\n"
                    f"Chaves restantes: **{remaining_keys}**\n\n"
                    f"Tempo estimado para conclusão: **{str(datetime.timedelta(seconds=estimated_remaining_seconds)).split('.')[0]}**\n\n"
                    f"Conclusão esperada por volta de: **{estimated_finish_time.strftime('%H:%M:%S de %d/%m/%Y')}**"
                )
                current_request_text.text(f"Consultando CNPJ para chave: {key} ({i + 1}/{total_keys})")

                # Validação básica da chave
                if len(key) != 44 or not key.isdigit():
                    results.append({
                        "Chave de Acesso": key,
                        "UF": "Chave Inválida",
                        "Ano/Mês Emissão": "Chave Inválida",
                        "CNPJ Emitente": "Chave Inválida",
                        "Modelo Doc.": "Chave Inválida",
                        "Série": "Chave Inválida",
                        "Número NF-e": "Chave Inválida",
                        "Tipo Emissão": "Chave Inválida",
                        "Código Numérico": "Chave Inválida",
                        "Dígito Verificador": "Chave Inválida",
                        "Regime Tributário": "Chave Inválida"
                    })
                    continue # Pula para a próxima chave
                
                parsed_data = parse_nfe_key(key)
                cnpj_to_query = parsed_data["CNPJ Emitente"]
                
                tax_regime = get_cnpj_tax_regime(cnpj_to_query)
                
                # Adiciona a chave original e o regime tributário aos dados parseados
                parsed_data["Chave de Acesso"] = key
                parsed_data["Regime Tributário"] = tax_regime
                
                results.append(parsed_data)
            
            # Limpa os elementos de status após a conclusão
            progress_bar.empty() 
            time_estimate_text.empty()
            current_request_text.empty()
            
            if results:
                df = pd.DataFrame(results)
                # Reorganiza as colunas na ordem desejada
                column_order = [
                    "Chave de Acesso", "UF", "Ano/Mês Emissão", "CNPJ Emitente",
                    "Modelo Doc.", "Série", "Número NF-e", "Tipo Emissão",
                    "Código Numérico", "Dígito Verificador", "Regime Tributário"
                ]
                # Garante que todas as colunas existem antes de reordenar
                for col in column_order:
                    if col not in df.columns:
                        df[col] = 'N/A' 
                
                df = df[column_order]
                
                st.session_state.nfe_results_df = df
                st.success("Processamento concluído!")
            else:
                st.warning("Nenhuma chave de acesso válida foi encontrada para processar.")
                st.session_state.nfe_results_df = pd.DataFrame()

# Exibe os resultados se houver dados no session_state
if "nfe_results_df" in st.session_state and not st.session_state.nfe_results_df.empty:
    st.subheader("Resultados da Análise")
    # Exibe o DataFrame de forma interativa
    st.dataframe(st.session_state.nfe_results_df, hide_index=True, use_container_width=True)
    
    st.markdown("---")
    st.subheader("Opções de Exportação")

    col1, col2 = st.columns(2) # Cria duas colunas para os botões de download

    with col1:
        # Botão de Download para Excel
        excel_output = io.BytesIO()
        with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
            st.session_state.nfe_results_df.to_excel(writer, index=False, sheet_name='Dados NFe')
        processed_excel_data = excel_output.getvalue()

        st.download_button(
            label="💾 Baixar como Excel",
            data=processed_excel_data,
            file_name=f"dados_nfe_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel_nfe"
        )
    
    with col2:
        # Botão de Download para CSV
        csv_output = st.session_state.nfe_results_df.to_csv(index=False, encoding='utf-8-sig') # 'utf-8-sig' para compatibilidade com acentuação no Excel
        
        st.download_button(
            label="📄 Baixar como CSV",
            data=csv_output,
            file_name=f"dados_nfe_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="download_csv_nfe"
        )
