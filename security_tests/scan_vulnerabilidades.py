"""
Scanner de Vulnerabilidades - Fortanks
=======================================
Script que realiza testes de segurança contra o sistema Fortanks.
Inclui análise estática do código-fonte e testes dinâmicos contra o endpoint live.

USO:
    python security_tests/scan_vulnerabilidades.py --url https://sfortanks.com:8043
    python security_tests/scan_vulnerabilidades.py --url https://sfortanks.com:8043 --email admin@email.com --senha 123456
    python security_tests/scan_vulnerabilidades.py --static-only
    python security_tests/scan_vulnerabilidades.py --url https://sfortanks.com:8043 --dynamic-only
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

try:
    import requests
    from requests.exceptions import SSLError, ConnectionError, Timeout
except ImportError:
    print("Instale o requests: pip install requests")
    sys.exit(1)

requests.packages.urllib3.disable_warnings()

BASE_DIR = Path(__file__).resolve().parent.parent


class Severidade(str, Enum):
    CRITICA = "CRITICA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"
    INFO = "INFO"


@dataclass
class Vulnerabilidade:
    titulo: str
    severidade: Severidade
    descricao: str
    localizacao: str = ""
    recomendacao: str = ""
    categoria: str = ""


@dataclass
class Relatorio:
    vulnerabilidades: list = field(default_factory=list)
    inicio: str = ""
    fim: str = ""
    url_alvo: str = ""

    def adicionar(self, vuln: Vulnerabilidade):
        self.vulnerabilidades.append(vuln)

    def resumo(self):
        contagem = {}
        for v in self.vulnerabilidades:
            contagem[v.severidade] = contagem.get(v.severidade, 0) + 1
        return contagem


# ============================================================
# PARTE 1 - ANÁLISE ESTÁTICA DO CÓDIGO-FONTE
# ============================================================

class AnalisadorEstatico:
    """Analisa o código-fonte em busca de padrões vulneráveis."""

    def __init__(self, base_dir: Path, relatorio: Relatorio):
        self.base_dir = base_dir
        self.relatorio = relatorio

    def executar(self):
        print("\n" + "=" * 60)
        print("  ANÁLISE ESTÁTICA DO CÓDIGO-FONTE")
        print("=" * 60)

        self._verificar_config()
        self._verificar_sql_injection()
        self._verificar_open_redirect()
        self._verificar_xss()
        self._verificar_info_leak()
        self._verificar_cors()
        self._verificar_csrf_exempt()
        self._verificar_upload_seguranca()
        self._verificar_permissoes_desativadas()
        self._verificar_debug_mode()
        self._verificar_rate_limiting()
        self._verificar_password_policy()
        self._verificar_session_config()

    def _ler_arquivo(self, caminho_relativo: str) -> Optional[str]:
        caminho = self.base_dir / caminho_relativo
        if caminho.exists():
            try:
                return caminho.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                return None
        return None

    def _buscar_arquivos(self, pasta: str, extensao: str = ".py") -> list:
        resultado = []
        caminho = self.base_dir / pasta
        if caminho.exists():
            for f in caminho.rglob(f"*{extensao}"):
                if '.venv' not in str(f) and '__pycache__' not in str(f):
                    resultado.append(f)
        return resultado

    def _verificar_config(self):
        print("\n[1/13] Verificando configurações de segurança...")

        config = self._ler_arquivo("config/config.py")
        if not config:
            return

        if "chave-secreta-padrao" in config:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="SECRET_KEY com valor padrão hardcoded",
                severidade=Severidade.CRITICA,
                descricao="A SECRET_KEY possui um fallback hardcoded 'chave-secreta-padrao-deve-ser-alterada'. "
                          "Se a variável de ambiente não estiver definida, qualquer atacante pode forjar cookies de sessão.",
                localizacao="config/config.py:10",
                recomendacao="Remover o fallback e exigir que SECRET_KEY seja definida via variável de ambiente. "
                             "Gerar uma chave com: python -c \"import secrets; print(secrets.token_hex(32))\"",
                categoria="Configuração"
            ))

        if "DEBUG = True" in config and "class Config:" in config:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="DEBUG habilitado na configuração base",
                severidade=Severidade.ALTA,
                descricao="DEBUG=True na classe Config base. Se ProductionConfig não sobrescrever, "
                          "mensagens de erro detalhadas com stacktrace serão expostas em produção.",
                localizacao="config/config.py:11",
                recomendacao="Definir DEBUG=False na Config base. Usar DEBUG=True apenas em DevelopmentConfig.",
                categoria="Configuração"
            ))

        if "SESSION_COOKIE_SECURE = False" in config:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="SESSION_COOKIE_SECURE desativado na configuração base",
                severidade=Severidade.MEDIA,
                descricao="Cookies de sessão podem ser transmitidos via HTTP não criptografado.",
                localizacao="config/config.py:36",
                recomendacao="Como o sistema usa HTTPS, garantir que SESSION_COOKIE_SECURE=True em produção.",
                categoria="Sessão"
            ))

        if "SESSION_COOKIE_SAMESITE" not in config:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="SESSION_COOKIE_SAMESITE não configurado",
                severidade=Severidade.MEDIA,
                descricao="Sem SameSite nos cookies, o navegador pode enviar cookies em requisições cross-site.",
                localizacao="config/config.py",
                recomendacao="Adicionar SESSION_COOKIE_SAMESITE = 'Lax' na configuração.",
                categoria="Sessão"
            ))

        if "MAX_CONTENT_LENGTH = 150" in config:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Limite de upload muito alto (150MB)",
                severidade=Severidade.BAIXA,
                descricao="O limite de 150MB para uploads pode facilitar ataques de DoS por esgotamento de recursos.",
                localizacao="config/config.py:29",
                recomendacao="Avaliar se 150MB é realmente necessário. Reduzir para o mínimo necessário.",
                categoria="Configuração"
            ))

        if "PASSWORD_MIN_LENGTH = 8" in config:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Tamanho mínimo de senha pode ser insuficiente",
                severidade=Severidade.BAIXA,
                descricao="Senhas de 8 caracteres sem exigência de complexidade são vulneráveis a ataques de dicionário.",
                localizacao="config/config.py:35",
                recomendacao="Aumentar para 12+ caracteres e exigir complexidade (maiúsculas, números, especiais).",
                categoria="Autenticação"
            ))

    def _verificar_sql_injection(self):
        print("[2/13] Verificando SQL Injection...")

        arquivos = self._buscar_arquivos("controllers")
        for arq in arquivos:
            try:
                conteudo = arq.read_text(encoding='utf-8', errors='ignore')
                linhas = conteudo.split('\n')
                for i, linha in enumerate(linhas, 1):
                    if re.search(r'text\(f["\']', linha) or re.search(r'text\(.*%\s', linha):
                        rel_path = arq.relative_to(self.base_dir)
                        self.relatorio.adicionar(Vulnerabilidade(
                            titulo=f"Possível SQL Injection via string interpolation",
                            severidade=Severidade.CRITICA,
                            descricao=f"Uso de f-string ou formatação % dentro de text(), "
                                      f"permitindo injeção SQL: {linha.strip()[:120]}",
                            localizacao=f"{rel_path}:{i}",
                            recomendacao="Usar parâmetros nomeados: text('SELECT ... WHERE id = :id'), {{'id': valor}}",
                            categoria="SQL Injection"
                        ))
            except Exception:
                continue

    def _verificar_open_redirect(self):
        print("[3/13] Verificando Open Redirect...")

        auth_code = self._ler_arquivo("controllers/auth_controller.py")
        if auth_code and "next_page = request.args.get('next')" in auth_code:
            if "url_has_allowed_host_and_scheme" not in auth_code and "is_safe_url" not in auth_code:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Open Redirect na rota de login",
                    severidade=Severidade.ALTA,
                    descricao="O parâmetro 'next' no login é usado em redirect() sem validação. "
                              "Um atacante pode redirecionar: /login?next=https://evil.com",
                    localizacao="controllers/auth_controller.py:54-56",
                    recomendacao="Validar que a URL é relativa e pertence ao mesmo domínio usando "
                                 "url_has_allowed_host_and_scheme() do Werkzeug.",
                    categoria="Open Redirect"
                ))

        for arq in self._buscar_arquivos("controllers"):
            try:
                conteudo = arq.read_text(encoding='utf-8', errors='ignore')
                linhas = conteudo.split('\n')
                for i, linha in enumerate(linhas, 1):
                    if 'redirect(' in linha and 'request.form.get' in linha:
                        if "startswith('/')" not in conteudo[max(0, conteudo.find(linha) - 200):conteudo.find(linha) + 200]:
                            rel_path = arq.relative_to(self.base_dir)
                            self.relatorio.adicionar(Vulnerabilidade(
                                titulo="Possível Open Redirect via form data",
                                severidade=Severidade.MEDIA,
                                descricao=f"Redirect usando dados do formulário sem validação completa.",
                                localizacao=f"{rel_path}:{i}",
                                recomendacao="Validar que URLs de redirecionamento são internas ao sistema.",
                                categoria="Open Redirect"
                            ))
            except Exception:
                continue

    def _verificar_xss(self):
        print("[4/13] Verificando XSS (Cross-Site Scripting)...")

        templates = self._buscar_arquivos("templates", ".html")
        for arq in templates:
            try:
                conteudo = arq.read_text(encoding='utf-8', errors='ignore')
                linhas = conteudo.split('\n')
                for i, linha in enumerate(linhas, 1):
                    if '|safe' in linha and '{{' in linha:
                        rel_path = arq.relative_to(self.base_dir)
                        self.relatorio.adicionar(Vulnerabilidade(
                            titulo="Uso do filtro |safe no template (potencial XSS)",
                            severidade=Severidade.MEDIA,
                            descricao=f"O filtro |safe desabilita o auto-escape do Jinja2: {linha.strip()[:100]}",
                            localizacao=f"{rel_path}:{i}",
                            recomendacao="Verificar se os dados passados para |safe são sanitizados no backend. "
                                         "Usar bleach.clean() se necessário.",
                            categoria="XSS"
                        ))
            except Exception:
                continue

        for arq in self._buscar_arquivos("controllers"):
            try:
                conteudo = arq.read_text(encoding='utf-8', errors='ignore')
                linhas = conteudo.split('\n')
                for i, linha in enumerate(linhas, 1):
                    if 'Markup(' in linha:
                        rel_path = arq.relative_to(self.base_dir)
                        self.relatorio.adicionar(Vulnerabilidade(
                            titulo="Uso de Markup() no controller (potencial XSS)",
                            severidade=Severidade.MEDIA,
                            descricao=f"Markup() marca string como segura, bypassando auto-escape.",
                            localizacao=f"{rel_path}:{i}",
                            recomendacao="Sanitizar o conteúdo antes de wrappear com Markup().",
                            categoria="XSS"
                        ))
            except Exception:
                continue

    def _verificar_info_leak(self):
        print("[5/13] Verificando vazamento de informações...")

        auth_code = self._ler_arquivo("controllers/auth_controller.py")
        if auth_code and "print(f'usuario:" in auth_code and "senha" in auth_code:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Senha do usuário impressa em logs/console",
                severidade=Severidade.CRITICA,
                descricao="A rota de login imprime email e senha em texto claro via print(). "
                          "Isso expõe credenciais nos logs do servidor.",
                localizacao="controllers/auth_controller.py:37",
                recomendacao="Remover imediatamente o print() que expõe credenciais.",
                categoria="Vazamento de Informação"
            ))

        app_code = self._ler_arquivo("app.py")
        if app_code and "print(os.getenv('DATABASE_URI'))" in app_code:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="URI do banco de dados impressa no console",
                severidade=Severidade.ALTA,
                descricao="A string de conexão do banco (com credenciais) é impressa na inicialização.",
                localizacao="app.py:402",
                recomendacao="Remover o print(os.getenv('DATABASE_URI')).",
                categoria="Vazamento de Informação"
            ))

        config_code = self._ler_arquivo("config/config.py")
        if config_code:
            match = re.search(r'mysql\+pymysql://\w+:.*@[\d.]+:\d+/\w+', config_code)
            if match:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Credenciais de banco hardcoded no código-fonte",
                    severidade=Severidade.ALTA,
                    descricao=f"String de conexão com IP interno e padrão de senha no código: {match.group()[:60]}...",
                    localizacao="config/config.py:17",
                    recomendacao="Usar exclusivamente variáveis de ambiente para credenciais.",
                    categoria="Vazamento de Informação"
                ))

    def _verificar_cors(self):
        print("[6/13] Verificando configuração CORS...")

        app_code = self._ler_arquivo("app.py")
        if app_code and "CORS(app)" in app_code:
            if 'origins=' not in app_code or "origins=['*']" in app_code:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="CORS configurado para aceitar qualquer origem",
                    severidade=Severidade.ALTA,
                    descricao="CORS(app) sem restrição de origens permite que qualquer site faça "
                              "requisições ao sistema, podendo vazar dados se combinado com credenciais.",
                    localizacao="app.py:125",
                    recomendacao="Restringir origens: CORS(app, origins=['https://sfortanks.com:8043'])",
                    categoria="CORS"
                ))

    def _verificar_csrf_exempt(self):
        print("[7/13] Verificando isenções de CSRF...")

        app_code = self._ler_arquivo("app.py")
        if app_code and "@csrf.exempt" in app_code:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Rotas isentas de proteção CSRF",
                severidade=Severidade.MEDIA,
                descricao="Existem rotas marcadas como csrf.exempt (/concretagens/api/tanques/pecas, "
                          "/concretagens/api/concretagem). Ataques CSRF podem modificar dados nessas rotas.",
                localizacao="app.py:133-144",
                recomendacao="Reavaliar se a isenção é necessária. Usar tokens CSRF em chamadas AJAX via header.",
                categoria="CSRF"
            ))

    def _verificar_upload_seguranca(self):
        print("[8/13] Verificando segurança de uploads...")

        upload_code = self._ler_arquivo("controllers/upload_controller.py")
        if upload_code:
            if 'allowed_extensions' not in upload_code.lower() and 'allowed_files' not in upload_code.lower():
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Upload sem validação de tipo de arquivo",
                    severidade=Severidade.ALTA,
                    descricao="O controller de upload não valida extensões de arquivo permitidas. "
                              "Arquivos maliciosos (.py, .php, .exe) podem ser enviados.",
                    localizacao="controllers/upload_controller.py",
                    recomendacao="Implementar whitelist de extensões permitidas e validar MIME type real.",
                    categoria="Upload"
                ))

            if 'secure_filename' not in upload_code:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Upload sem sanitização do nome do arquivo",
                    severidade=Severidade.MEDIA,
                    descricao="Não há uso de secure_filename() do Werkzeug no controller de upload.",
                    localizacao="controllers/upload_controller.py",
                    recomendacao="Usar secure_filename() para sanitizar nomes de arquivos enviados.",
                    categoria="Upload"
                ))

    def _verificar_permissoes_desativadas(self):
        print("[9/13] Verificando sistema de permissões...")

        app_code = self._ler_arquivo("app.py")
        if app_code and "if False:" in app_code and "verificar_permissao" in app_code:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Sistema de permissões granulares desativado",
                severidade=Severidade.ALTA,
                descricao="O verificar_permissao() no before_request está desativado (if False:). "
                          "Qualquer usuário autenticado pode acessar qualquer funcionalidade.",
                localizacao="app.py:257-260",
                recomendacao="Ativar e configurar o sistema de permissões granulares.",
                categoria="Autorização"
            ))

    def _verificar_debug_mode(self):
        print("[10/13] Verificando modo debug...")

        app_code = self._ler_arquivo("app.py")
        if app_code and "#sslify = SSLify(app)" in app_code:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="SSLify comentado/desativado",
                severidade=Severidade.MEDIA,
                descricao="A forçar HTTPS via SSLify está comentada. "
                          "Requisições HTTP podem ser aceitas sem redirecionamento.",
                localizacao="app.py:89",
                recomendacao="Habilitar SSLify em produção ou garantir redirecionamento HTTPS no proxy reverso.",
                categoria="Configuração"
            ))

    def _verificar_rate_limiting(self):
        print("[11/13] Verificando rate limiting...")

        app_code = self._ler_arquivo("app.py")
        config_code = self._ler_arquivo("config/config.py")
        combined = (app_code or '') + (config_code or '')

        if 'limiter' not in combined.lower() and 'ratelimit' not in combined.lower():
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Ausência de rate limiting",
                severidade=Severidade.ALTA,
                descricao="Não há rate limiting implementado. Ataques de força bruta no login, "
                          "enumeração de usuários e DoS ficam facilitados.",
                localizacao="app.py / config/config.py",
                recomendacao="Implementar Flask-Limiter. Exemplo: limiter.limit('5/minute') na rota de login.",
                categoria="Autenticação"
            ))

    def _verificar_password_policy(self):
        print("[12/13] Verificando políticas de senha...")

        auth_code = self._ler_arquivo("controllers/auth_controller.py")
        if auth_code:
            if 'account_lock' not in auth_code and 'tentativas' not in auth_code and 'attempts' not in auth_code:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Sem bloqueio de conta após tentativas falhas",
                    severidade=Severidade.ALTA,
                    descricao="A rota de login não bloqueia após tentativas falhas consecutivas.",
                    localizacao="controllers/auth_controller.py",
                    recomendacao="Implementar bloqueio temporário após 5 tentativas falhas (ex: 15 minutos).",
                    categoria="Autenticação"
                ))

    def _verificar_session_config(self):
        print("[13/13] Verificando configuração de sessão...")

        config_code = self._ler_arquivo("config/config.py")
        if config_code and "REMEMBER_COOKIE_HTTPONLY" not in config_code:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="REMEMBER_COOKIE_HTTPONLY não configurado",
                severidade=Severidade.BAIXA,
                descricao="Se 'remember me' for usado, o cookie pode ser acessível via JavaScript.",
                localizacao="config/config.py",
                recomendacao="Adicionar REMEMBER_COOKIE_HTTPONLY = True.",
                categoria="Sessão"
            ))


# ============================================================
# PARTE 2 - TESTES DINÂMICOS (CONTRA O SERVIDOR LIVE)
# ============================================================

class TesterDinamico:
    """Executa testes de segurança contra o servidor em execução."""

    def __init__(self, base_url: str, relatorio: Relatorio, email: str = "", senha: str = ""):
        self.base_url = base_url.rstrip('/')
        self.relatorio = relatorio
        self.email = email
        self.senha = senha
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Fortanks-SecurityScanner/1.0'
        })
        self.autenticado = False

    def executar(self):
        print("\n" + "=" * 60)
        print("  TESTES DINÂMICOS CONTRA O SERVIDOR")
        print(f"  Alvo: {self.base_url}")
        print("=" * 60)

        self._teste_conectividade()
        self._teste_headers_seguranca()
        self._teste_metodos_http()
        self._teste_ssl_tls()
        self._teste_info_disclosure()
        self._teste_open_redirect()
        self._teste_cors()
        self._teste_brute_force_login()
        self._teste_enumeracao_usuarios()
        self._teste_session_fixation()
        self._teste_csrf_token()
        self._teste_sql_injection_login()
        self._teste_xss_refletido()
        self._teste_directory_traversal()
        self._teste_idor()
        self._teste_clickjacking()
        self._teste_rotas_sensiveis()

    def _request(self, method: str, path: str, **kwargs) -> Optional[requests.Response]:
        url = f"{self.base_url}{path}"
        kwargs.setdefault('timeout', 15)
        kwargs.setdefault('allow_redirects', False)
        try:
            return self.session.request(method, url, **kwargs)
        except (SSLError, ConnectionError, Timeout) as e:
            print(f"    [ERRO] Falha na requisição {method} {path}: {e}")
            return None

    def _autenticar(self) -> bool:
        if self.autenticado:
            return True
        if not self.email or not self.senha:
            print("    [INFO] Credenciais não fornecidas, pulando testes autenticados.")
            return False

        r = self._request('GET', '/login')
        if not r:
            return False

        csrf_token = self._extrair_csrf(r.text)
        data = {'email': self.email, 'senha': self.senha}
        if csrf_token:
            data['csrf_token'] = csrf_token

        r = self._request('POST', '/login', data=data, allow_redirects=True)
        if r and r.status_code == 200 and 'dashboard' in r.url:
            self.autenticado = True
            print("    [OK] Autenticação bem-sucedida.")
            return True
        print("    [AVISO] Falha na autenticação. Testes autenticados serão limitados.")
        return False

    def _extrair_csrf(self, html: str) -> str:
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        if match:
            return match.group(1)
        match = re.search(r'csrf_token.*?value="([^"]+)"', html, re.DOTALL)
        if match:
            return match.group(1)
        return ""

    def _teste_conectividade(self):
        print("\n[1/17] Testando conectividade...")
        r = self._request('GET', '/')
        if r:
            print(f"    [OK] Servidor respondeu: HTTP {r.status_code}")
        else:
            print("    [FALHA] Servidor inacessível!")
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Servidor inacessível",
                severidade=Severidade.INFO,
                descricao=f"Não foi possível conectar em {self.base_url}",
                categoria="Conectividade"
            ))

    def _teste_headers_seguranca(self):
        print("[2/17] Testando headers de segurança...")
        r = self._request('GET', '/login')
        if not r:
            return

        headers_esperados = {
            'X-Content-Type-Options': ('nosniff', Severidade.MEDIA),
            'X-Frame-Options': ('DENY ou SAMEORIGIN', Severidade.MEDIA),
            'X-XSS-Protection': ('1; mode=block', Severidade.BAIXA),
            'Strict-Transport-Security': ('max-age=...', Severidade.ALTA),
            'Content-Security-Policy': ('default-src...', Severidade.MEDIA),
            'Referrer-Policy': ('strict-origin-when-cross-origin', Severidade.BAIXA),
            'Permissions-Policy': ('geolocation=()...', Severidade.BAIXA),
        }

        for header, (valor_esperado, severidade) in headers_esperados.items():
            if header.lower() not in {k.lower(): v for k, v in r.headers.items()}:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo=f"Header de segurança ausente: {header}",
                    severidade=severidade,
                    descricao=f"O header {header} não está presente na resposta. Valor esperado: {valor_esperado}",
                    localizacao=f"GET /login → Response Headers",
                    recomendacao=f"Adicionar o header {header} via middleware Flask ou proxy reverso (Nginx).",
                    categoria="Headers HTTP"
                ))

        server = r.headers.get('Server', '')
        if server:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo=f"Header Server expõe tecnologia: '{server}'",
                severidade=Severidade.BAIXA,
                descricao="O header Server revela informações sobre o software do servidor.",
                localizacao="Response Headers",
                recomendacao="Remover ou ofuscar o header Server no proxy reverso.",
                categoria="Headers HTTP"
            ))

    def _teste_metodos_http(self):
        print("[3/17] Testando métodos HTTP perigosos...")
        for metodo in ['OPTIONS', 'TRACE', 'PUT', 'DELETE', 'PATCH']:
            r = self._request(metodo, '/')
            if r and r.status_code not in (405, 404, 301, 302, 308):
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo=f"Método HTTP {metodo} aceito na raiz",
                    severidade=Severidade.BAIXA,
                    descricao=f"{metodo} / retornou HTTP {r.status_code}",
                    recomendacao="Desabilitar métodos HTTP desnecessários.",
                    categoria="Métodos HTTP"
                ))

    def _teste_ssl_tls(self):
        print("[4/17] Testando SSL/TLS...")
        try:
            r = requests.get(self.base_url + '/login', timeout=10, verify=True)
            print("    [OK] Certificado SSL válido.")
        except SSLError as e:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Certificado SSL inválido ou auto-assinado",
                severidade=Severidade.ALTA,
                descricao=f"Erro de validação SSL: {str(e)[:200]}",
                localizacao=self.base_url,
                recomendacao="Usar certificado SSL válido (Let's Encrypt é gratuito).",
                categoria="SSL/TLS"
            ))
        except Exception:
            pass

        http_url = self.base_url.replace('https://', 'http://').replace(':8043', ':8080')
        try:
            r = requests.get(http_url, timeout=5, allow_redirects=False, verify=False)
            if r.status_code != 301 and r.status_code != 302:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="HTTP não redireciona para HTTPS",
                    severidade=Severidade.MEDIA,
                    descricao=f"Requisição HTTP em {http_url} retornou {r.status_code} sem redirecionar para HTTPS.",
                    recomendacao="Configurar redirecionamento 301 de HTTP para HTTPS.",
                    categoria="SSL/TLS"
                ))
        except Exception:
            pass

    def _teste_info_disclosure(self):
        print("[5/17] Testando vazamento de informações...")

        rotas_teste = [
            '/admin/', '/debug/', '/console/', '/.env', '/config',
            '/static/.env', '/robots.txt', '/sitemap.xml',
            '/.git/HEAD', '/.git/config',
            '/static/uploads/', '/logs/', '/migrations/',
            '/api/', '/swagger/', '/docs/',
        ]

        for rota in rotas_teste:
            r = self._request('GET', rota)
            if r and r.status_code == 200:
                tamanho = len(r.text)
                if tamanho > 50:
                    severidade = Severidade.ALTA if rota in ('/.env', '/.git/HEAD', '/.git/config') else Severidade.MEDIA
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo=f"Rota sensível acessível: {rota}",
                        severidade=severidade,
                        descricao=f"GET {rota} retornou HTTP 200 com {tamanho} bytes de conteúdo.",
                        localizacao=f"GET {rota}",
                        recomendacao="Bloquear acesso a rotas sensíveis via configuração do servidor web.",
                        categoria="Vazamento de Informação"
                    ))

        r = self._request('GET', '/pagina-que-nao-existe-12345')
        if r and r.text:
            indicadores_debug = ['Traceback', 'Debugger', 'WSGI', 'werkzeug', 'File "/', 'line ']
            for ind in indicadores_debug:
                if ind in r.text:
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo="Informações de debug expostas em páginas de erro",
                        severidade=Severidade.ALTA,
                        descricao=f"Página 404 expõe informação de debug: encontrado '{ind}'",
                        localizacao="GET /pagina-que-nao-existe-12345",
                        recomendacao="Desativar DEBUG em produção e usar páginas de erro customizadas.",
                        categoria="Vazamento de Informação"
                    ))
                    break

    def _teste_open_redirect(self):
        print("[6/17] Testando Open Redirect...")

        payloads_redirect = [
            '/login?next=https://evil.com',
            '/login?next=//evil.com',
            '/login?next=https%3A%2F%2Fevil.com',
            '/login?next=/\\evil.com',
        ]

        for payload in payloads_redirect:
            r = self._request('GET', payload)
            if r and r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get('Location', '')
                if 'evil.com' in location:
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo="Open Redirect confirmado no login",
                        severidade=Severidade.ALTA,
                        descricao=f"Payload: {payload}\nLocation: {location}",
                        localizacao="GET /login?next=...",
                        recomendacao="Validar que o parâmetro next é uma URL relativa interna.",
                        categoria="Open Redirect"
                    ))
                    break

    def _teste_cors(self):
        print("[7/17] Testando CORS...")

        origens_teste = [
            'https://evil.com',
            'https://attacker.com',
            'null',
        ]

        for origem in origens_teste:
            r = self._request('GET', '/login', headers={'Origin': origem})
            if r:
                acao = r.headers.get('Access-Control-Allow-Origin', '')
                cred = r.headers.get('Access-Control-Allow-Credentials', '')

                if acao == '*' or acao == origem:
                    sev = Severidade.CRITICA if cred.lower() == 'true' else Severidade.ALTA
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo=f"CORS aceita origem maliciosa: {origem}",
                        severidade=sev,
                        descricao=f"Access-Control-Allow-Origin: {acao}, "
                                  f"Access-Control-Allow-Credentials: {cred}",
                        localizacao=f"Origin: {origem}",
                        recomendacao="Restringir CORS para aceitar apenas origens confiáveis.",
                        categoria="CORS"
                    ))
                    break

    def _teste_brute_force_login(self):
        print("[8/17] Testando resistência a brute force no login...")

        r = self._request('GET', '/login')
        if not r:
            return

        csrf_token = self._extrair_csrf(r.text)
        bloqueou = False
        senhas_teste = [f"senha_errada_{i}" for i in range(10)]

        for i, senha in enumerate(senhas_teste):
            data = {'email': 'teste@teste.com', 'senha': senha}
            if csrf_token:
                data['csrf_token'] = csrf_token

            r = self._request('POST', '/login', data=data, allow_redirects=True)
            if r and r.status_code == 429:
                bloqueou = True
                print(f"    [OK] Rate limiting ativou após {i + 1} tentativas.")
                break

            if r:
                csrf_token = self._extrair_csrf(r.text)

            time.sleep(0.3)

        if not bloqueou:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Login sem proteção contra brute force",
                severidade=Severidade.ALTA,
                descricao="10 tentativas de login falhas consecutivas não geraram bloqueio (HTTP 429).",
                localizacao="POST /login",
                recomendacao="Implementar rate limiting (Flask-Limiter) e/ou bloqueio temporário de conta.",
                categoria="Autenticação"
            ))

    def _teste_enumeracao_usuarios(self):
        print("[9/17] Testando enumeração de usuários...")

        r = self._request('GET', '/login')
        if not r:
            return
        csrf_token = self._extrair_csrf(r.text)

        data_invalido = {'email': 'naoexiste_xyz123@test.com', 'senha': 'abc123'}
        if csrf_token:
            data_invalido['csrf_token'] = csrf_token
        r1 = self._request('POST', '/login', data=data_invalido, allow_redirects=True)
        msg1 = r1.text if r1 else ""

        r = self._request('GET', '/login')
        csrf_token = self._extrair_csrf(r.text) if r else ""
        data_valido = {'email': 'admin@fortanks.com', 'senha': 'abc123'}
        if csrf_token:
            data_valido['csrf_token'] = csrf_token
        r2 = self._request('POST', '/login', data=data_valido, allow_redirects=True)
        msg2 = r2.text if r2 else ""

        if r1 and r2:
            msg_usuario_inv = "Email ou senha incorretos" in msg1 or "incorretos" in msg1
            msg_usuario_val = "incorretos" in msg2 or "senha incorreta" in msg2.lower()

            if "não encontrado" in msg1.lower() or "usuário inexistente" in msg1.lower():
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Enumeração de usuários possível via mensagens de erro",
                    severidade=Severidade.MEDIA,
                    descricao="As mensagens de erro para email válido e inválido são diferentes, "
                              "permitindo determinar quais emails estão cadastrados.",
                    localizacao="POST /login",
                    recomendacao="Usar mensagem genérica: 'Email ou senha incorretos' para ambos os casos.",
                    categoria="Autenticação"
                ))

    def _teste_session_fixation(self):
        print("[10/17] Testando session fixation...")

        r = self._request('GET', '/login')
        if not r:
            return

        cookies_antes = dict(self.session.cookies)
        session_antes = cookies_antes.get('session', '')

        if self.email and self.senha:
            csrf_token = self._extrair_csrf(r.text)
            data = {'email': self.email, 'senha': self.senha}
            if csrf_token:
                data['csrf_token'] = csrf_token
            r = self._request('POST', '/login', data=data, allow_redirects=True)

            cookies_depois = dict(self.session.cookies)
            session_depois = cookies_depois.get('session', '')

            if session_antes and session_depois and session_antes == session_depois:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Session Fixation: cookie de sessão não regenerado após login",
                    severidade=Severidade.ALTA,
                    descricao="O ID da sessão não muda após autenticação bem-sucedida.",
                    localizacao="POST /login",
                    recomendacao="Regenerar o cookie de sessão após login com session.regenerate().",
                    categoria="Sessão"
                ))

    def _teste_csrf_token(self):
        print("[11/17] Testando proteção CSRF...")

        r = self._request('GET', '/login')
        if not r:
            return

        csrf_token = self._extrair_csrf(r.text)
        if not csrf_token:
            self.relatorio.adicionar(Vulnerabilidade(
                titulo="Token CSRF não encontrado no formulário de login",
                severidade=Severidade.ALTA,
                descricao="O formulário de login não contém campo csrf_token.",
                localizacao="GET /login",
                recomendacao="Incluir {{ csrf_token() }} em todos os formulários.",
                categoria="CSRF"
            ))

        data = {'email': 'teste@teste.com', 'senha': 'teste', 'csrf_token': 'token_invalido_xyz'}
        r = self._request('POST', '/login', data=data, allow_redirects=True)
        if r and r.status_code != 400:
            if 'CSRF' not in r.text and 'csrf' not in r.text.lower():
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Proteção CSRF pode não estar validando corretamente",
                    severidade=Severidade.MEDIA,
                    descricao=f"Login com CSRF token inválido retornou HTTP {r.status_code} sem erro CSRF.",
                    localizacao="POST /login",
                    recomendacao="Verificar se CSRFProtect está validando tokens corretamente.",
                    categoria="CSRF"
                ))

    def _teste_sql_injection_login(self):
        print("[12/17] Testando SQL Injection no login...")

        r = self._request('GET', '/login')
        if not r:
            return

        payloads = [
            ("' OR '1'='1' --", "OR 1=1"),
            ("admin@test.com' UNION SELECT 1,2,3--", "UNION"),
            ("'; DROP TABLE usuarios; --", "DROP TABLE"),
            ("' AND 1=CONVERT(int,(SELECT @@version))--", "CONVERT"),
        ]

        for payload, nome in payloads:
            csrf_token = self._extrair_csrf(r.text if r else "")
            data = {'email': payload, 'senha': 'teste'}
            if csrf_token:
                data['csrf_token'] = csrf_token

            r2 = self._request('POST', '/login', data=data, allow_redirects=True)
            if r2:
                indicadores_sqli = ['syntax error', 'mysql', 'SQL', 'operand', 'ORM', 'sqlalchemy']
                for ind in indicadores_sqli:
                    if ind.lower() in r2.text.lower():
                        self.relatorio.adicionar(Vulnerabilidade(
                            titulo=f"Possível SQL Injection no login (payload: {nome})",
                            severidade=Severidade.CRITICA,
                            descricao=f"O servidor retornou mensagem contendo '{ind}' para payload: {payload[:50]}",
                            localizacao="POST /login",
                            recomendacao="Usar queries parametrizadas e nunca interpolar input do usuário em SQL.",
                            categoria="SQL Injection"
                        ))
                        break

            r = self._request('GET', '/login')
            time.sleep(0.3)

    def _teste_xss_refletido(self):
        print("[13/17] Testando XSS refletido...")

        xss_payloads = [
            '<script>alert("XSS")</script>',
            '"><img src=x onerror=alert(1)>',
            "'-alert(1)-'",
            '<svg/onload=alert(1)>',
        ]

        rotas_teste = ['/login', '/usuarios', '/clientes']

        for rota in rotas_teste:
            for payload in xss_payloads:
                encoded = urllib.parse.quote(payload)
                r = self._request('GET', f'{rota}?q={encoded}&search={encoded}')
                if r and payload in r.text:
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo=f"XSS Refletido em {rota}",
                        severidade=Severidade.ALTA,
                        descricao=f"O payload XSS foi refletido sem escape na resposta.",
                        localizacao=f"GET {rota}?q={payload[:30]}...",
                        recomendacao="Garantir auto-escape no Jinja2 e sanitizar inputs.",
                        categoria="XSS"
                    ))
                    break

    def _teste_directory_traversal(self):
        print("[14/17] Testando Directory Traversal...")

        payloads = [
            '/uploads/download/../../../etc/passwd',
            '/static/../../etc/passwd',
            '/static/uploads/../../config/config.py',
            '/uploads/download/..%2f..%2f..%2fetc%2fpasswd',
        ]

        for payload in payloads:
            r = self._request('GET', payload)
            if r and r.status_code == 200:
                if 'root:' in r.text or 'SECRET_KEY' in r.text:
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo="Directory Traversal confirmado",
                        severidade=Severidade.CRITICA,
                        descricao=f"Payload {payload} retornou conteúdo sensível.",
                        localizacao=f"GET {payload}",
                        recomendacao="Sanitizar caminhos de arquivo e usar os.path.realpath() para validação.",
                        categoria="Directory Traversal"
                    ))
                    break

    def _teste_idor(self):
        print("[15/17] Testando IDOR (Insecure Direct Object Reference)...")

        rotas_idor = [
            '/uploads/download/1',
            '/uploads/download/2',
            '/api/tanques/1',
            '/colaboradores/1',
            '/usuarios/1',
        ]

        for rota in rotas_idor:
            r = self._request('GET', rota)
            if r and r.status_code == 200:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo=f"IDOR potencial: {rota} acessível",
                    severidade=Severidade.MEDIA,
                    descricao=f"GET {rota} retornou HTTP 200. Verificar se controle de acesso por usuário está implementado.",
                    localizacao=f"GET {rota}",
                    recomendacao="Implementar verificação de que o recurso pertence ao usuário autenticado.",
                    categoria="IDOR"
                ))

    def _teste_clickjacking(self):
        print("[16/17] Testando Clickjacking...")

        r = self._request('GET', '/login')
        if r:
            xfo = r.headers.get('X-Frame-Options', '')
            csp = r.headers.get('Content-Security-Policy', '')

            if not xfo and 'frame-ancestors' not in csp:
                self.relatorio.adicionar(Vulnerabilidade(
                    titulo="Vulnerável a Clickjacking",
                    severidade=Severidade.MEDIA,
                    descricao="Sem X-Frame-Options ou CSP frame-ancestors, o site pode ser embutido em iframe malicioso.",
                    localizacao="Response Headers",
                    recomendacao="Adicionar X-Frame-Options: DENY e/ou CSP com frame-ancestors 'self'.",
                    categoria="Clickjacking"
                ))

    def _teste_rotas_sensiveis(self):
        print("[17/17] Testando acesso a rotas administrativas sem autorização...")

        rotas_admin = [
            '/admin/',
            '/admin/permissoes',
            '/admin/banco',
            '/usuarios/',
            '/dashboard/',
        ]

        sess_nova = requests.Session()
        sess_nova.verify = False

        for rota in rotas_admin:
            try:
                r = sess_nova.get(f"{self.base_url}{rota}", timeout=10, allow_redirects=False)
                if r.status_code == 200:
                    self.relatorio.adicionar(Vulnerabilidade(
                        titulo=f"Rota administrativa acessível sem autenticação: {rota}",
                        severidade=Severidade.CRITICA,
                        descricao=f"GET {rota} retornou HTTP 200 sem sessão autenticada.",
                        localizacao=f"GET {rota}",
                        recomendacao="Garantir que @login_required ou before_request protege todas as rotas admin.",
                        categoria="Autenticação"
                    ))
            except Exception:
                continue


# ============================================================
# PARTE 3 - GERADOR DE RELATÓRIO
# ============================================================

class GeradorRelatorio:
    """Gera relatório em HTML e texto."""

    @staticmethod
    def gerar_texto(relatorio: Relatorio) -> str:
        linhas = []
        linhas.append("=" * 70)
        linhas.append("  RELATÓRIO DE VULNERABILIDADES - FORTANKS")
        linhas.append("=" * 70)
        linhas.append(f"  URL Alvo: {relatorio.url_alvo}")
        linhas.append(f"  Início:   {relatorio.inicio}")
        linhas.append(f"  Fim:      {relatorio.fim}")
        linhas.append(f"  Total:    {len(relatorio.vulnerabilidades)} vulnerabilidades encontradas")
        linhas.append("")

        resumo = relatorio.resumo()
        linhas.append("  RESUMO POR SEVERIDADE:")
        marcadores = {
            Severidade.CRITICA: "[!!!]",
            Severidade.ALTA: "[!! ]",
            Severidade.MEDIA: "[!  ]",
            Severidade.BAIXA: "[.  ]",
            Severidade.INFO: "[   ]",
        }
        for sev in Severidade:
            count = resumo.get(sev, 0)
            linhas.append(f"    {marcadores.get(sev, '')} {sev.value}: {count}")

        linhas.append("")
        linhas.append("-" * 70)

        for i, v in enumerate(relatorio.vulnerabilidades, 1):
            linhas.append(f"\n  [{v.severidade.value}] #{i}: {v.titulo}")
            linhas.append(f"  Categoria:     {v.categoria}")
            if v.localizacao:
                linhas.append(f"  Localização:   {v.localizacao}")
            linhas.append(f"  Descrição:     {v.descricao}")
            if v.recomendacao:
                linhas.append(f"  Recomendação:  {v.recomendacao}")
            linhas.append("  " + "-" * 66)

        return "\n".join(linhas)

    @staticmethod
    def gerar_html(relatorio: Relatorio) -> str:
        cores = {
            Severidade.CRITICA: "#dc3545",
            Severidade.ALTA: "#fd7e14",
            Severidade.MEDIA: "#ffc107",
            Severidade.BAIXA: "#0d6efd",
            Severidade.INFO: "#6c757d",
        }
        resumo = relatorio.resumo()

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Vulnerabilidades - Fortanks</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 10px; color: #e94560; font-size: 1.8rem; }}
        .meta {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 0.9rem; }}
        .summary {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-bottom: 30px; }}
        .summary-card {{ padding: 15px 25px; border-radius: 10px; text-align: center; min-width: 120px; }}
        .summary-card .count {{ font-size: 2rem; font-weight: bold; }}
        .summary-card .label {{ font-size: 0.8rem; text-transform: uppercase; }}
        .vuln-card {{ background: #16213e; border-radius: 10px; padding: 20px; margin-bottom: 15px;
                      border-left: 5px solid; }}
        .vuln-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .vuln-title {{ font-size: 1.1rem; font-weight: 600; }}
        .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: bold; color: #fff; }}
        .vuln-meta {{ font-size: 0.85rem; color: #888; margin-bottom: 8px; }}
        .vuln-desc {{ line-height: 1.6; margin-bottom: 10px; }}
        .vuln-rec {{ background: #0f3460; padding: 12px; border-radius: 8px; font-size: 0.9rem; }}
        .vuln-rec strong {{ color: #e94560; }}
        .filter-bar {{ display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-bottom: 20px; }}
        .filter-btn {{ padding: 6px 16px; border-radius: 20px; border: 2px solid; cursor: pointer;
                       background: transparent; color: #eee; font-size: 0.85rem; transition: 0.2s; }}
        .filter-btn:hover, .filter-btn.active {{ background: #e94560; border-color: #e94560; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Relatório de Vulnerabilidades</h1>
    <p class="meta">
        Alvo: {relatorio.url_alvo} | Início: {relatorio.inicio} | Fim: {relatorio.fim} |
        Total: {len(relatorio.vulnerabilidades)} vulnerabilidades
    </p>
    <div class="summary">"""

        for sev in Severidade:
            count = resumo.get(sev, 0)
            cor = cores[sev]
            html += f"""
        <div class="summary-card" style="background: {cor}22; border: 1px solid {cor};">
            <div class="count" style="color: {cor};">{count}</div>
            <div class="label">{sev.value}</div>
        </div>"""

        html += """
    </div>
    <div class="filter-bar">
        <button class="filter-btn active" onclick="filtrar('all')">Todos</button>"""

        for sev in Severidade:
            html += f"""
        <button class="filter-btn" onclick="filtrar('{sev.value}')" style="border-color: {cores[sev]};">{sev.value}</button>"""

        html += """
    </div>
    <div id="vulns">"""

        for i, v in enumerate(relatorio.vulnerabilidades, 1):
            cor = cores[v.severidade]
            html += f"""
        <div class="vuln-card" data-sev="{v.severidade.value}" style="border-left-color: {cor};">
            <div class="vuln-header">
                <span class="vuln-title">#{i} {v.titulo}</span>
                <span class="badge" style="background: {cor};">{v.severidade.value}</span>
            </div>
            <div class="vuln-meta">{v.categoria}{(' | ' + v.localizacao) if v.localizacao else ''}</div>
            <div class="vuln-desc">{v.descricao}</div>"""
            if v.recomendacao:
                html += f"""
            <div class="vuln-rec"><strong>Recomendação:</strong> {v.recomendacao}</div>"""
            html += """
        </div>"""

        html += """
    </div>
</div>
<script>
function filtrar(sev) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.vuln-card').forEach(c => {
        c.style.display = (sev === 'all' || c.dataset.sev === sev) ? 'block' : 'none';
    });
}
</script>
</body>
</html>"""
        return html

    @staticmethod
    def salvar(relatorio: Relatorio, pasta_saida: Path):
        pasta_saida.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        txt_path = pasta_saida / f"relatorio_{timestamp}.txt"
        txt_path.write_text(GeradorRelatorio.gerar_texto(relatorio), encoding='utf-8')

        html_path = pasta_saida / f"relatorio_{timestamp}.html"
        html_path.write_text(GeradorRelatorio.gerar_html(relatorio), encoding='utf-8')

        json_path = pasta_saida / f"relatorio_{timestamp}.json"
        dados_json = {
            "url_alvo": relatorio.url_alvo,
            "inicio": relatorio.inicio,
            "fim": relatorio.fim,
            "total": len(relatorio.vulnerabilidades),
            "resumo": {k.value: v for k, v in relatorio.resumo().items()},
            "vulnerabilidades": [
                {
                    "id": i,
                    "titulo": v.titulo,
                    "severidade": v.severidade.value,
                    "categoria": v.categoria,
                    "localizacao": v.localizacao,
                    "descricao": v.descricao,
                    "recomendacao": v.recomendacao,
                }
                for i, v in enumerate(relatorio.vulnerabilidades, 1)
            ]
        }
        json_path.write_text(json.dumps(dados_json, ensure_ascii=False, indent=2), encoding='utf-8')

        print(f"\n  Relatórios salvos em: {pasta_saida}")
        print(f"    - {txt_path.name}")
        print(f"    - {html_path.name}")
        print(f"    - {json_path.name}")

        return txt_path, html_path, json_path


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scanner de Vulnerabilidades - Fortanks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python security_tests/scan_vulnerabilidades.py --url https://sfortanks.com:8043
  python security_tests/scan_vulnerabilidades.py --url https://sfortanks.com:8043 --email admin@email.com --senha 123456
  python security_tests/scan_vulnerabilidades.py --static-only
  python security_tests/scan_vulnerabilidades.py --url https://sfortanks.com:8043 --dynamic-only
        """
    )
    parser.add_argument('--url', default='https://sfortanks.com:8043', help='URL base do sistema')
    parser.add_argument('--email', default='', help='Email para testes autenticados')
    parser.add_argument('--senha', default='', help='Senha para testes autenticados')
    parser.add_argument('--static-only', action='store_true', help='Executar apenas análise estática')
    parser.add_argument('--dynamic-only', action='store_true', help='Executar apenas testes dinâmicos')
    parser.add_argument('--output', default='security_tests/resultados', help='Pasta de saída dos relatórios')

    args = parser.parse_args()

    relatorio = Relatorio(url_alvo=args.url)
    relatorio.inicio = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print("\n" + "=" * 60)
    print("  SCANNER DE VULNERABILIDADES - FORTANKS")
    print("=" * 60)
    print(f"  Alvo:         {args.url}")
    print(f"  Início:       {relatorio.inicio}")
    print(f"  Modo:         ", end="")
    if args.static_only:
        print("Apenas Análise Estática")
    elif args.dynamic_only:
        print("Apenas Testes Dinâmicos")
    else:
        print("Completo (Estático + Dinâmico)")

    if not args.dynamic_only:
        analisador = AnalisadorEstatico(BASE_DIR, relatorio)
        analisador.executar()

    if not args.static_only:
        tester = TesterDinamico(args.url, relatorio, args.email, args.senha)
        tester.executar()

    relatorio.fim = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print("\n" + GeradorRelatorio.gerar_texto(relatorio))

    pasta_saida = Path(args.output)
    GeradorRelatorio.salvar(relatorio, pasta_saida)


if __name__ == '__main__':
    main()
