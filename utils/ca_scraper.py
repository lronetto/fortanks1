import requests
import re
import logging
import json
from datetime import datetime, date
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CONSULTACA_ORIGIN = "https://consultaca.com"


def _headers_consultaca_navegador(referer: str | None = None, same_origin: bool = False) -> dict:
    """Cabeçalhos próximos de um Chrome recente (UA antigo costuma levar 403 em WAF/CDN)."""
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if same_origin else "none",
        "Sec-Fetch-User": "?1",
        'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        'Sec-Ch-Ua-Platform': '"Windows"',
    }
    if referer:
        h["Referer"] = referer
    return h


def baixar_pagina_consultaca(url: str) -> tuple[str | None, str | None]:
    """
    Obtém o HTML de uma URL do consultaca.com.
    Usa sessão + página inicial (cookies) e, em 403, tenta cloudscraper (Cloudflare/WAF).
    Retorna (html, None) ou (None, mensagem_erro).
    """
    headers_inicial = _headers_consultaca_navegador()
    session = requests.Session()
    session.headers.update(headers_inicial)

    try:
        session.get(
            f"{CONSULTACA_ORIGIN}/",
            timeout=15,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.debug("Warm-up consultaca.com ignorado: %s", e)

    headers_ca = _headers_consultaca_navegador(
        referer=f"{CONSULTACA_ORIGIN}/",
        same_origin=True,
    )

    try:
        response = session.get(url, headers=headers_ca, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        logger.error("Erro na requisição HTTP (requests): %s", e)
        return None, f"Erro ao acessar o site: {str(e)}"

    if response.status_code == 200:
        return response.text, None

    if response.status_code == 403:
        logger.warning(
            "consultaca.com retornou 403 com requests; tentando cloudscraper (URL=%s)",
            url,
        )
        try:
            import cloudscraper  # type: ignore[import-untyped]
        except ImportError:
            return None, (
                "Falha ao acessar o site: 403. Instale cloudscraper (pip install cloudscraper) "
                "ou atualize dependências do projeto."
            )

        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            scraper.headers.update(headers_inicial)
            scraper.get(f"{CONSULTACA_ORIGIN}/", timeout=15, allow_redirects=True)
            r2 = scraper.get(url, headers=headers_ca, timeout=15, allow_redirects=True)
        except Exception as e:
            logger.error("cloudscraper falhou: %s", e, exc_info=True)
            return None, f"Falha ao acessar o site: 403 ({e})"

        if r2.status_code == 200:
            return r2.text, None
        return None, f"Falha ao acessar o site: {r2.status_code}"

    logger.error("Falha ao acessar o site: %s", response.status_code)
    return None, f"Falha ao acessar o site: {response.status_code}"


def consultar_ca(numero_ca):
    """
    Realiza consulta de um CA no site consultaca.com via webscraping
    
    Args:
        numero_ca (str): Número do CA a ser consultado
        
    Returns:
        dict: Dicionário com informações do CA ou None se não encontrado
    """
    try:
        # Formatando o número do CA (removendo caracteres não numéricos)
        numero_ca = re.sub(r'[^\d]', '', str(numero_ca))
        
        if not numero_ca:
            return {"erro": "Número de CA inválido"}
        
        url = f"{CONSULTACA_ORIGIN}/{numero_ca}"

        logger.info("Consultando CA %s em %s", numero_ca, url)

        html_content, erro_http = baixar_pagina_consultaca(url)
        if erro_http:
            return {"erro": erro_http}
        
        # Verificar se o CA não foi encontrado
        if "não foi encontrado" in html_content.lower() or "inválido" in html_content.lower():
            logger.info(f"CA {numero_ca} não encontrado")
            return {"erro": "CA não encontrado ou inválido"}
        
        # Inicializar o dicionário de dados
        dados = {"numero_ca": numero_ca}
        
        try:
            # ---- EXTRAÇÃO POR BEAUTIFULSOUP + REGEX ESPECÍFICOS ----
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extrair informações de metadados
            meta_description = soup.find('meta', attrs={'name': 'description'})
            if meta_description and meta_description.get('content'):
                description_content = meta_description.get('content')
                # Tentar extrair título do EPI
                if not dados.get("equipamento") and "CA" in description_content:
                    title_match = re.search(r'CA\s+\d+\s*[-:]\s*([^|]+)', description_content)
                    if title_match:
                        dados["equipamento"] = limpar_texto(title_match.group(1))
            
            # Extrair título/nome do EPI
            if not dados.get("equipamento"):
                # Tentar h1 primeiro
                h1 = soup.find('h1')
                if h1:
                    dados["equipamento"] = limpar_texto(h1.get_text())
                else:
                    # Tentar h2
                    h2 = soup.find('h2')
                    if h2:
                        dados["equipamento"] = limpar_texto(h2.get_text())
                    else:
                        # Tentar título da página
                        title = soup.find('title')
                        if title:
                            title_text = title.get_text()
                            # Limpar prefixos como "ConsultaCA - "
                            title_text = re.sub(r'^ConsultaCA\s*[-:]\s*', '', title_text)
                            # Limpar o número do CA se estiver no título
                            title_text = re.sub(r'CA\s*\d+\s*[-:]\s*', '', title_text)
                            dados["equipamento"] = limpar_texto(title_text)
            
            # Procurar em div's ou p's com informações de fabricante e situação
            info_containers = soup.find_all(['div', 'p', 'span', 'li'])
            for container in info_containers:
                text = container.get_text()
                
                # Buscar fabricante
                if not dados.get("fabricante") and re.search(r'fabricante|empresa|marca', text, re.IGNORECASE):
                    fabricante_match = re.search(r'(?:fabricante|empresa|marca)\s*[:-]\s*([^,\n]+)', text, re.IGNORECASE)
                    if fabricante_match:
                        dados["fabricante"] = limpar_texto(fabricante_match.group(1))
                
                # Buscar situação
                if not dados.get("situacao") and re.search(r'situação|status', text, re.IGNORECASE):
                    situacao_match = re.search(r'(?:situação|status)\s*[:-]\s*([^,\n]+)', text, re.IGNORECASE)
                    if situacao_match:
                        dados["situacao"] = limpar_texto(situacao_match.group(1))
                
                # Buscar data de validade
                if not dados.get("data_validade") and re.search(r'validade|vencimento', text, re.IGNORECASE):
                    validade_match = re.search(r'(?:validade|vencimento)\s*[:-]\s*(\d{2}\/\d{2}\/\d{4})', text, re.IGNORECASE)
                    if validade_match:
                        data_str = validade_match.group(1)
                        try:
                            data_obj = datetime.strptime(data_str, "%d/%m/%Y").date()
                            # Converter para string formatada para evitar problemas de serialização
                            dados["data_validade"] = data_obj.strftime("%Y-%m-%d")
                        except ValueError:
                            dados["data_validade_texto"] = data_str
                
                # Buscar descrição
                if not dados.get("descricao") and re.search(r'descrição|especificação|detalhes', text, re.IGNORECASE):
                    descricao_match = re.search(r'(?:descrição|especificação|detalhes)\s*[:-]\s*([^\n]+)', text, re.IGNORECASE)
                    if descricao_match:
                        dados["descricao"] = limpar_texto(descricao_match.group(1))
                
                # Buscar normas aplicáveis
                if not dados.get("normas") and re.search(r'normas?|aprovado para', text, re.IGNORECASE):
                    normas_match = re.search(r'(?:normas?|aprovado para)\s*[:-]\s*([^\n]+)', text, re.IGNORECASE)
                    if normas_match:
                        normas_text = limpar_texto(normas_match.group(1))
                        normas = re.split(r',|;|\n', normas_text)
                        dados["normas"] = [norma.strip() for norma in normas if norma.strip()]
            
            # Buscar em blocos de texto separados (para casos onde os dados estão em elementos diferentes)
            all_text = soup.get_text()
            
            # Tentar encontrar fabricante em todo o texto
            if not dados.get("fabricante"):
                fabricante_match = re.search(r'(?:fabricante|empresa|marca)\s*[:-]\s*([^,\n\.]+)', all_text, re.IGNORECASE)
                if fabricante_match:
                    dados["fabricante"] = limpar_texto(fabricante_match.group(1))
            
            # Tentar encontrar situação em todo o texto
            if not dados.get("situacao"):
                situacao_match = re.search(r'(?:situação|status)\s*[:-]\s*([^,\n\.]+)', all_text, re.IGNORECASE)
                if situacao_match:
                    dados["situacao"] = limpar_texto(situacao_match.group(1))
            
            # Buscar por texto que começa com CA seguido do número
            # Muitas vezes após isso vem o título do EPI
            if not dados.get("equipamento"):
                ca_pattern = fr'CA\s*{numero_ca}\s*[-–:]\s*([^\n\.]+)'
                ca_match = re.search(ca_pattern, all_text, re.IGNORECASE)
                if ca_match:
                    dados["equipamento"] = limpar_texto(ca_match.group(1))
            
            # Tentar extrair valores de tabelas
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text().lower()
                        value = cells[1].get_text()
                        
                        if 'fabricante' in label or 'empresa' in label:
                            dados["fabricante"] = limpar_texto(value)
                        elif 'situação' in label or 'status' in label:
                            dados["situacao"] = limpar_texto(value)
                        elif 'validade' in label or 'vencimento' in label:
                            validade_match = re.search(r'(\d{2}/\d{2}/\d{4})', value)
                            if validade_match:
                                try:
                                    data_obj = datetime.strptime(validade_match.group(1), "%d/%m/%Y").date()
                                    # Converter para string formatada
                                    dados["data_validade"] = data_obj.strftime("%Y-%m-%d")
                                except ValueError:
                                    dados["data_validade_texto"] = validade_match.group(1)
        except Exception as parsing_error:
            logger.error(f"Erro ao extrair dados do HTML: {str(parsing_error)}", exc_info=True)
            # Continuar com os dados já coletados, sem interromper por erro de parsing
        
        # ---- VALORES PADRÃO ----
        # Garantir que temos pelo menos valores padrão para os campos importantes
        if not dados.get("equipamento"):
            dados["equipamento"] = f"CA {numero_ca}"
        
        if not dados.get("fabricante"):
            dados["fabricante"] = "Não identificado"
            
        if not dados.get("situacao"):
            dados["situacao"] = "Não identificado"
            
        if not dados.get("descricao"):
            dados["descricao"] = "Sem descrição disponível"
        
        # Converter qualquer objeto date para string antes do log
        _dados_log = dados.copy()
        for key, value in _dados_log.items():
            if isinstance(value, (date, datetime)):
                _dados_log[key] = value.strftime("%Y-%m-%d")
        
        # Log dos dados obtidos
        logger.info(f"CA {numero_ca} consultado com sucesso: {json.dumps(_dados_log)}")
        return dados
    
    except Exception as e:
        logger.error(f"Erro ao consultar CA {numero_ca}: {str(e)}", exc_info=True)
        return {"erro": f"Erro ao processar a consulta: {str(e)}"}

# Função auxiliar para serializar objetos date/datetime para JSON
def json_serial(obj):
    """Função para serializar objetos date/datetime para JSON"""
    if isinstance(obj, (datetime, date)):
        return obj.strftime('%Y-%m-%d')
    raise TypeError(f"Type {type(obj)} not serializable")

def limpar_texto(texto):
    """Limpa um texto HTML, removendo tags e espaços extras"""
    if not texto:
        return ""
    # Remover tags HTML
    texto = re.sub(r'<[^>]*>', ' ', texto)
    # Remover espaços extras, quebras de linha, etc
    texto = re.sub(r'\s+', ' ', texto)
    # Remover espaços no início e fim
    texto = texto.strip()
    # Remover ":" no final (comum em labels)
    texto = re.sub(r':$', '', texto)
    return texto

def validar_ca(numero_ca):
    """
    Verifica se um CA é válido consultando o site
    
    Args:
        numero_ca (str): Número do CA a ser validado
        
    Returns:
        bool: True se o CA for válido e estiver na situação 'Válido', False caso contrário
    """
    resultado = consultar_ca(numero_ca)
    
    if resultado and not resultado.get("erro"):
        situacao = resultado.get("situacao", "").lower()
        return "válido" in situacao or "valido" in situacao
    
    return False 