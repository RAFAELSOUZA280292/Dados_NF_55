import streamlit as st
import requests
import pandas as pd
import re
import datetime
import io
import time # Para pausas em caso de erro 429 da API
import os   # Para verificar a existência do arquivo de logo

# --- Configuração da Página ---
st.set_page_config(page_title="Dados NF-55", layout="wide") # Layout 'wide' para melhor visualização da tabela

# --- Adicionar o Logo ---
# Caminho para o logo. Por padrão, o Streamlit busca caminhos relativos ao diretório do script.
# Se 'images_2' está na raiz do seu projeto Streamlit, este caminho está correto.
logo_path = "images_2/logo.png" 

if os.path.exists(logo_path):
    st.image(logo_path, width=400) # Ajuste a largura conforme necessário
else:
    st.warning(f"O arquivo de logo não foi encontrado em '{logo_path}'. Verifique o caminho.")

# --- Custom CSS para o Tema (Copiado do seu app CNPJ para consistência) ---
st.markdown("""
<style>
/* Fundo geral do app e cor do texto padrão para tema claro */
.stApp {
    background-color: #F8F9FA; /* Cinza muito claro, quase branco */
    color: #333333; /* Cinza escuro para texto padrão */
}

/* Títulos (h1, h2, h3, h5) */
h1, h2, h3, h5 {
    color: #00ACC1; /* Azul Ciano para todos os títulos relevantes */
}

/* Fundo dos campos de entrada de texto (textarea, text_input) */
.st-emotion-cache-z5fcl4, /* Container primário do input */
.st-emotion-cache-1oe5f0g, /* Caixa de texto do input */
.st-emotion-cache-13vmq3j, /* Outra classe comum de input */
.st-emotion-cache-1g0b27k, /* Outra classe comum de input */
.st-emotion-cache-f0f7f3 /* Classe de textarea */
{
    background-color: white; /* Fundo branco para campos de entrada */
    color: #333333; /* Cor escura para o texto digitado */
    border-radius: 5px;
    border: 1px solid #ced4da; /* Borda cinza clara */
}

/* Caixa de informação (st.info) */
div[data-testid="stAlert"] {
    background-color: #e0f7fa; /* Fundo ciano claro */
    color: #004d40; /* Texto verde-azulado escuro para bom contraste */
    border-left: 5px solid #00ACC1; /* Borda ciano para destaque */
    border-radius: 5px;
}

/* Estilo dos Botões */
.stButton>button {
    background-color: #00ACC1; /* Fundo ciano */
    color: white; /* Texto branco para contraste */
    border-radius: 5px;
    border: none;
    padding: 10px 20px;
    font-size: 16px;
    cursor: pointer;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2); /* Sombra sutil para profundidade */
    transition: background-color 0.3s ease; /* Transição suave no hover */
}
.stButton>button:hover {
    background-color: #008C9E; /* Ciano ligeiramente mais escuro no hover */
}

/* Estilo das Tabs (não usado neste app, mas mantido para consistência) */
div[data-testid="stTabs"] {
    background-color: #F0F2F6;
    border-radius: 5px;
    border-bottom: 1px solid #ced4da;
}

button[data-testid^="stTab"] {
    color: #555555;
    background-color: #F0F2F6;
    font-weight: bold;
    padding: 10px 15px;
    border-radius: 5px 5px 0 0;
    margin-right: 2px;
    transition: background-color 0.3s ease, color 0.3s ease, border-bottom 0.3s ease;
}

button[data-testid^="stTab"][aria-selected="true"] {
    color: #00ACC1;
    background-color: white;
    border-bottom: 3px solid #00ACC1;
}
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

    url = f"https://open.cnpja.com/office/{clean_cnpj_num}"
    try:
        # Adiciona um timeout para evitar que a requisição trave indefinidamente
        response = requests.get(url, timeout=10) 

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
            st.warning(f"Muitas requisições para CNPJ {clean_cnpj_num} (Código 429). Tentando novamente em 5 segundos...")
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
            # Barra de progresso para feedback visual
            progress_bar = st.progress(0, text="Processando chaves de acesso...")
            
            for i, key in enumerate(cleaned_keys):
                # Atualiza a barra de progresso
                progress_bar.progress((i + 1) / len(cleaned_keys), text=f"Processando chave {i+1} de {len(cleaned_keys)}...")
                
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
            
            progress_bar.empty() # Remove a barra de progresso ao finalizar
            
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