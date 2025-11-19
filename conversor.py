import json
import openpyxl
import os

# Nomes dos arquivos
ARQUIVO_ENTRADA = "estatisticas_pacotes_raspados.json"
ARQUIVO_SAIDA = "estatisticas_pacotes_raspados.xlsx"

def converter_json_para_excel():
    # 1. Verifica se o arquivo JSON existe
    if not os.path.exists(ARQUIVO_ENTRADA):
        print(f"❌ Erro: O arquivo '{ARQUIVO_ENTRADA}' não foi encontrado.")
        return

    print(f"Lendo dados de '{ARQUIVO_ENTRADA}'...")
    
    try:
        # 2. Carrega o JSON
        with open(ARQUIVO_ENTRADA, 'r', encoding='utf-8') as f:
            dados_lista = json.load(f)
        
        print(f"Processando {len(dados_lista)} registros...")

        # 3. Cria o arquivo Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Relatório PyPI"

        # 4. Define os cabeçalhos
        cabecalhos = ["Nome Biblioteca", "Link PyPI", "Downloads (Mês)", "Data Último Lançamento"]
        ws.append(cabecalhos)

        # 5. Preenche as linhas
        for item in dados_lista:
            # Extrai metadados do scraper
            meta = item.get('metadados_scraper', {})
            # Extrai resposta da API
            stats_response = item.get('resposta_api_stats')

            # Pega os campos com valores padrão caso faltem
            nome = meta.get('nome_biblioteca', 'N/A')
            link = meta.get('link_pypi', 'N/A')
            data_lancamento = meta.get('data_ultima_modificacao', 'N/A')

            # Extrai downloads mensais com segurança
            downloads_mensais = 0
            if stats_response and 'data' in stats_response:
                downloads_mensais = stats_response['data'].get('last_month', 0)

            # Adiciona a linha na planilha
            ws.append([nome, link, downloads_mensais, data_lancamento])

        # 6. Salva o arquivo
        wb.save(ARQUIVO_SAIDA)
        print(f"✅ Sucesso! Arquivo Excel gerado: '{ARQUIVO_SAIDA}'")

    except Exception as e:
        print(f"❌ Ocorreu um erro durante a conversão: {e}")

if __name__ == "__main__":
    converter_json_para_excel()