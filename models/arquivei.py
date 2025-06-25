import requests
from dotenv import load_dotenv
import os
import base64
from flask import jsonify
from datetime import datetime, timedelta
import logging
import json
from models.logs import Logs

load_dotenv()


ARQUIVEI_API_ID = os.getenv('ARQUIVEI_API_ID')
ARQUIVEI_API_KEY = os.getenv('ARQUIVEI_API_KEY')
class Arquivei: 
    pdf = None
    chave_acesso = None
    xml_data = None
    data_inicial = None
    data_final = None
    xml_datas = []
    cancelada = False
    tipo = 'nfe'
    
    def __init__(self, data_inicial=None, data_final=None, chave_acesso=None, xml_data=None,cancelamento=False,send=False,tipo='nfe'):
        self.chave_acesso = chave_acesso
        self.xml_data = xml_data
        self.data_inicial = data_inicial
        self.data_final = data_final
        self.xml_datas = []
        self.pdf = None
        self.cancelada = False
        self.tipo = tipo
        if xml_data:
            self.xml_data = xml_data
            self.upload()
        if data_inicial and data_final:
            print(f'processando arquivei {tipo}')
            self.processar_arquivei()
        if chave_acesso and cancelamento==False:
            if int(chave_acesso[20:22]) == 57:
                self.tipo = 'cte'
            self.get()
        if chave_acesso and cancelamento:
            self.cancelada = self.cancelamento()
        if send:
            self.processar_arquivei(send=True)

    def upload(self):
        headers = {
                    'X-API-ID': ARQUIVEI_API_ID,
                    'X-API-KEY': ARQUIVEI_API_KEY,
                    'Content-Type': 'application/json'
                }
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
        headers = {
            'X-API-ID': ARQUIVEI_API_ID,
            'X-API-KEY': ARQUIVEI_API_KEY,
            'Content-Type': 'application/json'
        }
        url = f"https://api.arquivei.com.br/v2/nfe/events?access_key={self.chave_acesso}"
        response = requests.get(url, headers=headers)
        response=response.json()
        if response.get('status').get('code') == 200:
            if response.get('data'):
                for event in response.get('data'):
                    if event.get('type') == '110111':
                        return True
        return False
    
    def processar_arquivei(self,send=False):
        """
        Processa as notas fiscais da API do Arquivei
        """

                # Configurar cabeçalhos da API
        headers = {
            'X-API-ID': ARQUIVEI_API_ID,
            'X-API-KEY': ARQUIVEI_API_KEY,
            'Content-Type': 'application/json'
        }
        params = {}
        if self.data_inicial:
            params['created_at[from]'] = self.data_inicial
        if self.data_final:
            params['created_at[to]'] = self.data_final
        if self.tipo=='nfe':
            # Construir parâmetros da consulta
            params['document_type'] = 'nfe'
            if send:
                self.data_inicial = '2020-01-01'
                self.data_final = datetime.now().strftime("%Y-%m-%d")


           
            #print(params)
            # Executar a consulta na API

            if send:
                url = 'https://api.arquivei.com.br/v1/nfe/emitted'
            else:
                url = 'https://api.arquivei.com.br/v1/nfe/received'
        if self.tipo=='cte':
            url='https://api.arquivei.com.br/v1/cte/taker'

        
        response = requests.get(url, headers=headers, params=params)
        #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]} qtd: {len(response.json()["data"])} 1')
        #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]}')
            #print(response.json())
            
        # Processar cada nota fiscal
        notas_processadas = 0
        notas_ignoradas = 0
        
        if response.status_code == 200:
            response_data = response.json()
            #print('response_data: ',len(response_data['data']))
            #print('response_data: ',response_data)
            
            # Verificar se há dados retornados
            if 'data' not in response_data or not response_data['data']:
                return jsonify({'success': False, 'message': 'Nenhuma nota fiscal encontrada para o período especificado.'})
            #print(response_data)
            
            dt_inicial = datetime.strptime(self.data_inicial, "%Y-%m-%d")
            dt_final = datetime.strptime(self.data_final, "%Y-%m-%d")
           
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
                            if item.get('xml'):
                                xml_base64 = item.get('xml')
                                if not xml_base64:
                                    notas_ignoradas += 1
                                    continue
                                self.xml_datas.append(xml_base64)
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
                response = requests.get(url, headers=headers, params=params)
                #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]} qtd: {len(response.json()["data"])} 2')
                #print(f'data_fim: {data_fim} data_final: {dt_final}')
                while len(response.json()['data']) == 50:
                    
                    if(dt_final - data_fim).days > 20 and d > 20:
                        d-=10
                    else:
                        d-=5
                    data_ini = data_ini
                    data_fim = data_ini+timedelta(days=d)        
                    #print(f'dt_final - data_fim: {(dt_final - data_fim).days} d {d}')
                    params['created_at[from]'] = data_ini.strftime("%Y-%m-%d")
                    params['created_at[to]'] = data_fim.strftime("%Y-%m-%d")
                    response = requests.get(url, headers=headers, params=params)  
                    #print(f'data_ini: {params["created_at[from]"]} data_fim: {params["created_at[to]"]} qtd: {len(response.json()["data"])} 2')
                


            # Se alguma nota foi processada, mostrar mensagem de sucesso
            log = {
                'data_ini': self.data_inicial,
                'data_fim': self.data_final,
                'notas_processadas': notas_processadas,
                'notas_ignoradas': notas_ignoradas,
                'tipo': self.tipo
            }
            Logs(local='arquivei', data=datetime.now(), texto=json.dumps(log))
        else: 
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_msg += f' - {error_data["error"]}'
                if 'message' in error_data:
                    error_msg += f' - {error_data["message"]}'
                return jsonify({'success': False, 'message': error_msg})
            except:
                pass
    def get_xml(self):
        headers = {
            'X-API-ID': ARQUIVEI_API_ID,
            'X-API-KEY': ARQUIVEI_API_KEY,
            'Content-Type': 'application/json'
        }
        if self.tipo == 'cte':
            url = f"https://api.arquivei.com.br/v1/cte/taker?access_key[]={self.chave_acesso}"
        else:
            url = f"https://api.arquivei.com.br/v1/nfe/received?access_key[]={self.chave_acesso}"
        response = requests.get(url, headers=headers)
        response_data = response.json() 
        print('get xml')
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
        headers = {
            'X-API-ID': ARQUIVEI_API_ID,
            'X-API-KEY': ARQUIVEI_API_KEY,
            'Content-Type': 'application/json'
        }
        if self.tipo == 'cte':
            url = f"https://api.arquivei.com.br//v1/cte/dacte?access_key={self.chave_acesso}"
        else:
            url = f"https://api.arquivei.com.br/v1/nfe/danfe?access_key={self.chave_acesso}"
        response = requests.get(url, headers=headers)
        response_data = response.json() 
        print('get pdf')
        if response_data.get('status').get('code') == 200:
            self.pdf = response_data.get('data').get('encoded_pdf')
            #print('pdf: ',self._pdf)
    