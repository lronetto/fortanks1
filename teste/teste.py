import os
import unicodedata
import re
from pyzbar.pyzbar import decode
from pdf2image import convert_from_path

def normalizar_texto(texto):
    """
    Remove acentos e caracteres especiais do texto
    Exemplo: 'CENTRALFER - CENTRAL DE FERRO LTDA' -> 'CENTRALFER - CENTRAL DE FERRO LTDA'
    """
    if not texto:
        return texto
        
    # Normaliza o texto (NFKD) e remove os caracteres diacríticos
    texto = unicodedata.normalize('NFKD', texto)
    
    # Remove caracteres não ASCII
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    
    # Substitui caracteres específicos
    substituicoes = {
        'ç': 'c', 'Ç': 'C',
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
        'Á': 'A', 'À': 'A', 'Ã': 'A', 'Â': 'A', 'Ä': 'A',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
        'Ó': 'O', 'Ò': 'O', 'Õ': 'O', 'Ô': 'O', 'Ö': 'O',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'ý': 'y', 'ÿ': 'y',
        'Ý': 'Y', 'Ÿ': 'Y',
        'ñ': 'n', 'Ñ': 'N',
        '/': '.',  # Substitui / por .
        '\\': '.', # Substitui \ por .
        '&': 'E',  # Substitui & por E
        'E.': 'E', # Remove ponto após E
        ' S.A': ' SA', # Normaliza S.A
        ' S/A': ' SA', # Normaliza S/A
        ' LTDA': ' LTDA', # Normaliza LTDA
        ' ME': ' ME', # Normaliza ME
        ' EPP': ' EPP', # Normaliza EPP
        '.': '', # Remove ponto
    }
    
    for char, replacement in substituicoes.items():
        texto = texto.replace(char, replacement)
    
    # Remove espaços extras
    texto = ' '.join(texto.split())
    
    return texto

def extrair_numero_fornecedor_do_nome(nome_arquivo):
    """
    Extrai o número da nota fiscal e o nome do fornecedor do nome do arquivo
    Suporta os seguintes formatos:
    - O FORTE DOS PARAFUSOS E FERRAMENTAS LTDA - NF 298.590.pdf (Reembolso)
    - NF162.876 - ES PRODUTOS SIDERURGICOS LTDA.pdf (Protocolo)
    - 03-07-2025 - NF 80.540 - ARCELORMITTAL BRASIL S.A.pdf (Protocolo)
    - 08-06-2025 - NF 2810 - HOLANDA ENGENHARIA LTDA.pdf (Protocolo)
    - 09-06-2025 - FL 3364 - JACKTRACKER GEOPROCESSAMENTO LTDA.pdf (Protocolo)
    - Protocolo 264231708.pdf (Protocolo)
    """
    try:
        print(f"Processando arquivo: {nome_arquivo}")
        numero_nf = None
        fornecedor = None
        # Remove a extensão .pdf
        nome_sem_ext = nome_arquivo.replace('.pdf', '')
        print(f"Nome sem extensão: {nome_sem_ext}")
        
        # Se for um protocolo simples
        if nome_sem_ext.startswith('Protocolo'):
            numero_protocolo = nome_sem_ext.replace('Protocolo', '').strip()
            print(f"Protocolo simples encontrado: {numero_protocolo}")
            return numero_protocolo, 'PROTOCOLO'
        
        qtd_hifens = nome_sem_ext.count('-')
        if qtd_hifens == 1:
            #reembolso
            if '- NF' in nome_sem_ext:
                partes = nome_sem_ext.split(' - NF')
                print(f"Partes do nome (reembolso): {partes}")
                if len(partes) == 2:
                    fornecedor = partes[0].strip()
                    numero_nf = partes[1].replace('.', '').strip()
                    print(f"Reembolso encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
        else:
            #protocolo
            partes = nome_sem_ext.split(' - ')
            print(f"Partes do nome (protocolo): {partes}")
            if len(partes) == 3:
                fornecedor = partes[2].strip()
                partes[1] = partes[1].replace('.', '')
                delimitador = re.sub(r'\d', '', partes[1])
                numero_nf = partes[1].split(delimitador)[1].strip().replace('.', '')
                print(f"Protocolo encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
            elif len(partes) > 3:
                fornecedor = (partes[2]+' - '+partes[3]).strip()
                numero_nf = partes[1].split('NF')[1].strip().replace('.', '')
                print(f"Protocolo encontrado - Fornecedor: {fornecedor}, NF: {numero_nf}")
            else:
                print("Formato de protocolo inválido")
        
        if numero_nf and fornecedor:
            fornecedor = normalizar_texto(fornecedor)
            return numero_nf, fornecedor
        else:
            print("Formato de protocolo inválido")
            return None, None
    except Exception as e:
        print(f"Erro ao extrair número e fornecedor do nome do arquivo: {e}")
        return None, None
def main():

    pdfs = [i for i in os.listdir() if '.pdf' in i]
    img = convert_from_path(pdfs[0],500)[0]
    print(decode(img)[0].data.decode('utf-8'))
main()
