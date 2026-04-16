import requests
from datetime import datetime, timedelta
import logging

from models.nota_fiscal.constants import ARQUIVEI_API_ID, ARQUIVEI_API_KEY

logger = logging.getLogger(__name__)
class Arquivei: 
    pdf = None
    chave_acesso = None
    data = None
    data_inicial = None
    data_final = None
    xml_datas = []
    cancelada = False
    tipo = 'nfe'
    log_info = None
    datas = []
    id = None

    def __init__(
        self,
        data_inicial=None,
        chave_acesso=None,
        data_final=None,
        data=None,
        xml_data=None,
        cancelamento=False,
        send=False,
        tipo=None,
        pdf=None,
    ):
        self.data = data
        self.chave_acesso = chave_acesso
        self.id = None
        self.xml_data = None
        self.xml_datas = []
        self.datas = []
        self.pdf = None
        self.cancelada = False
        self.log_info = None

        if data:
            self.chave_acesso = data.get('chave_acesso', None)
            self.xml_data = data.get('xml', None)
            self.id = data.get('id', None)

        self.data_inicial = data_inicial
        self.data_final = data_final
        self.tipo = tipo

        if xml_data:
            self.xml_data = xml_data
            self.upload()

        if data_inicial and data_final and tipo:
            logger.info('processando arquivei %s', tipo)
            self.processar_periodo_completo()
            logger.info('datas carregadas: %s', len(self.datas))

        if self.chave_acesso:
            logger.debug('chave_acesso recebida: %s...', self.chave_acesso[:12])
            self._definir_tipo_por_chave()

            if pdf:
                self.get_pdf()
        if cancelamento:
            self.cancelada = self.cancelamento()
        if send:
            self.processar_arquivei(send=True)

    def _headers(self):
        return {
            'X-API-ID': ARQUIVEI_API_ID,
            'X-API-KEY': ARQUIVEI_API_KEY,
            'Content-Type': 'application/json',
        }

    def _definir_tipo_por_chave(self):
        if not self.chave_acesso:
            return

        if len(self.chave_acesso) == 44:
            try:
                modelo = int(self.chave_acesso[20:22])
            except ValueError:
                return
            if modelo == 57:
                self.tipo = 'cte'
            elif modelo == 55:
                self.tipo = 'nfe'
        elif len(self.chave_acesso) in (50, 32):
            # Mantém identificação por formato sem acoplar com NotaFiscal/query.
            self.tipo = 'nfse'

    def processar_periodo_completo(self):
        self.processar_arquivei(send=False)
        self.processar_arquivei(send=True)

    def upload(self):
        headers = self._headers()
        url="https://api.arquivei.com.br/v1/nfe/upload";
        payload = {
            "invoices":[
                {
                    "xml":f"{self.xml_data}"
                }
            ]
        }
        response = requests.request('POST',url, headers=headers, json=payload)
        #print(response.json())
        return response.json()

    def cancelamento(self):
        headers = self._headers()
        if self.tipo == 'cte':
            url = f"https://api.arquivei.com.br/v2/cte/events?access_key[]={self.chave_acesso}"
        elif self.tipo == 'nfe':
            url = f"https://api.arquivei.com.br/v2/nfe/events?access_key={self.chave_acesso}"
        elif self.tipo == 'nfse':
            url = f"https://api.arquivei.com.br/v1/nfse/events?access_key={self.chave_acesso}"
        else:
            logger.warning(
                'cancelamento Arquivei: tipo desconhecido %r para chave %s',
                self.tipo,
                (self.chave_acesso or '')[:12],
            )
            return False
        try:
            response = requests.get(url, headers=headers, timeout=60)
        except requests.RequestException as exc:
            logger.warning(
                'cancelamento Arquivei: falha na requisição: %s (chave %s...)',
                exc,
                (self.chave_acesso or '')[:12],
            )
            return False
        if response.status_code != 200:
            logger.warning(
                'cancelamento Arquivei: HTTP %s (chave %s...), corpo: %s',
                response.status_code,
                (self.chave_acesso or '')[:12],
                (response.text or '')[:400],
            )
            return False
        body = (response.text or '').strip()
        if not body:
            logger.warning(
                'cancelamento Arquivei: resposta vazia (chave %s...)',
                (self.chave_acesso or '')[:12],
            )
            return False
        try:
            data = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            logger.warning(
                'cancelamento Arquivei: corpo não é JSON (%s), início: %s',
                exc,
                body[:400],
            )
            return False
        status = data.get('status') if isinstance(data, dict) else None
        if not isinstance(status, dict) or status.get('code') != 200:
            return False
        if data.get('data'):
            for event in data.get('data'):
                if event.get('type') == '110111' or (
                    event.get('type') == '101101' and self.tipo == 'nfse'
                ):
                    return True
        return False
    
    def processar_arquivei(self,send=False):
        """
        Processa as notas fiscais da API do Arquivei
        """
        headers = self._headers()
        params = {}
        url = None
        query_data_inicial = self.data_inicial
        query_data_final = self.data_final

        if self.tipo=='nfe':
            # Construir parâmetros da consulta
            params['document_type'] = 'nfe'
            if send:
                query_data_inicial = '2020-01-01'
                query_data_final = datetime.now().strftime("%Y-%m-%d")
                url = 'https://api.arquivei.com.br/v1/nfe/emitted'
            else:
                url = 'https://api.arquivei.com.br/v1/nfe/received'
        if self.tipo=='cte':
            url='https://api.arquivei.com.br/v1/cte/taker'
        if self.tipo=='nfse':
            if send:
                url = 'https://api.arquivei.com.br/v1/nfse/emitted'
            else:
                url = 'https://api.arquivei.com.br/v1/nfse/received'
        if not url:
            self.log_info = {
                'success': False,
                'message': f'Tipo de documento inválido para processamento: {self.tipo}',
                'tipo': self.tipo,
                'send': send,
            }
            return self.log_info
        if query_data_inicial:
            params['created_at[from]'] = query_data_inicial
        if query_data_final:
            params['created_at[to]'] = query_data_final

        logger.debug('processar_arquivei url=%s params=%s', url, params)
        response = requests.get(url, headers=headers, params=params, timeout=60)
        #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]} qtd: {len(response.json()["data"])} 1')
        #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]}')
        #print(f'response: {response.json()}')
            
        # Processar cada nota fiscal
        notas_processadas = 0
        notas_ignoradas = 0
        
        if response.status_code == 200:
            response_data = response.json()
            #print('response_data: ',len(response_data['data']))
            #print('response_data: ',response_data)
            
            # Verificar se há dados retornados
            if 'data' not in response_data or not response_data['data']:
                self.log_info = {
                    'success': False,
                    'message': 'Nenhuma nota fiscal encontrada para o período especificado.',
                    'tipo': self.tipo,
                    'send': send,
                }
                return self.log_info
            #print(response_data)
            
            dt_inicial = datetime.strptime(query_data_inicial, "%Y-%m-%d")
            dt_final = datetime.strptime(query_data_final, "%Y-%m-%d")
           
            data_ini = dt_inicial
            data_fim = dt_inicial

            d=30
            notas_processadas = 0
            notas_ignoradas = 0
            xml_data = []
           
            while data_fim != dt_final or len(response.json()['data'])==50:
                
                i=0
                if response.status_code == 200:
                    
                    response_data = response.json()
                    if 'data' in response_data and response_data['data']:
                        for item in response_data['data']:
                            data = {
                                'xml': None,
                                'id': None,
                                'chave_acesso': None,
                            }
                            if item.get('xml'):
                                xml_base64 = item.get('xml')
                                if not xml_base64:
                                    notas_ignoradas += 1
                                    continue
                                data['xml'] = xml_base64
                                id = item.get('id',None)
                                if id:
                                    data['id'] = id
                                chave_acesso = item.get('access_key',None)
                                if chave_acesso:
                                    data['chave_acesso'] = chave_acesso
                                #print(f'item: {id}')
                                #print(f'chave_acesso: {chave_acesso}')
                                self.datas.append(data)
                                notas_processadas += 1
                            #print(f'processando nota fiscal {i}')
                            i+=1
                if (data_fim - dt_final).days <30:
                    d=(dt_final - data_fim).days
                else:
                    d=30
                data_ini = data_fim
                data_fim = data_fim+timedelta(days=d)
                #processar_nota_fiscal_xml(item.get('xml'))
                #print(f'processando notas {self.tipo} processadas: {notas_processadas} ignoradas: {notas_ignoradas}')
                params['created_at[from]'] = data_ini.strftime("%Y-%m-%d")
                params['created_at[to]'] = data_fim.strftime("%Y-%m-%d")
                response = requests.get(url, headers=headers, params=params, timeout=60)
                #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]} qtd: {len(response.json()["data"])} 2')
                #print(f'data_fim: {data_fim} data_final: {dt_final}')
                while len(response.json().get('data', [])) == 50:
                    
                    if(dt_final - data_fim).days > 20 and d > 20:
                        d-=10
                    else:
                        d-=5
                    data_ini = data_ini
                    data_fim = data_ini+timedelta(days=d)        
                    #print(f'dt_final - data_fim: {(dt_final - data_fim).days} d {d}')
                    params['created_at[from]'] = data_ini.strftime("%Y-%m-%d")
                    params['created_at[to]'] = data_fim.strftime("%Y-%m-%d")
                    response = requests.get(url, headers=headers, params=params, timeout=60)
                    #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]} qtd: {len(response.json()["data"])} 2')
                


            # Se alguma nota foi processada, mostrar mensagem de sucesso
            log = {
                'success': True,
                'data_ini': query_data_inicial,
                'data_fim': query_data_final,
                'notas_processadas': notas_processadas,
                'notas_ignoradas': notas_ignoradas,
                'tipo': self.tipo
            }
            self.log_info = log
            return log
        else: 
            try:
                error_data = response.json()
                error_msg = f'Erro ao consultar Arquivei (HTTP {response.status_code})'
                if 'error' in error_data:
                    error_msg += f' - {error_data["error"]}'
                if 'message' in error_data:
                    error_msg += f' - {error_data["message"]}'
                self.log_info = {
                    'success': False,
                    'message': error_msg,
                    'tipo': self.tipo,
                    'send': send,
                }
                return self.log_info
            except Exception:
                error_msg = f'Erro ao consultar Arquivei (HTTP {response.status_code})'
                self.log_info = {
                    'success': False,
                    'message': error_msg,
                    'tipo': self.tipo,
                    'send': send,
                }
                return self.log_info

    def get_xml(self):
        headers = self._headers()
        if self.tipo == 'cte':
            url = f"https://api.arquivei.com.br/v1/cte/taker?access_key[]={self.chave_acesso}"
        else:
            url = f"https://api.arquivei.com.br/v1/nfe/received?access_key[]={self.chave_acesso}"
        response = requests.get(url, headers=headers, timeout=60)
        response_data = response.json() 
        logger.debug('get_xml executado para tipo=%s', self.tipo)
        if response_data.get('status').get('code') == 200:
            if response_data.get('data'):
                for item in response_data.get('data'):
                    if item.get('xml'):
                        self.xml_data = item.get('xml')
                        break

    def get(self):
        self.get_xml()
        self.get_pdf()

    def get_pdf(self):
        headers = self._headers()
        logger.debug('get_pdf tipo=%s', self.tipo)
        if self.tipo == 'cte':
            url = f"https://api.arquivei.com.br//v1/cte/dacte?access_key={self.chave_acesso}"
        elif self.tipo == 'nfe':
            url = f"https://api.arquivei.com.br/v1/nfe/danfe?access_key={self.chave_acesso}"
        elif self.tipo == 'nfse':
            url = f"https://api.arquivei.com.br/v1/nfse/danfse?id={self.chave_acesso}"
        response = requests.get(url, headers=headers, timeout=60)
        response_data = response.json() 
       #print('get pdf')
        #print(f'url: {url}')
        #print(f'response_data: {response_data}')
        if response_data.get('status').get('code') == 200:
            self.pdf = response_data.get('data').get('encoded_pdf')
            #print('pdf: ',self._pdf)
    