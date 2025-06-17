import os
import sys
import base64
import json
from datetime import datetime
import xml.etree.ElementTree as ET

# Adicionar o diretório pai ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask
from config.config import Config
from models.database import db
from models.nota_fiscal import NotaFiscal

# Inicializa o app Flask e o contexto
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Função para extrair dados do CT-e

def extrair_dados_cte(xml_data):

    root = ET.fromstring(base64.b64decode(xml_data).decode('utf-8'))
    ns = {'cte': 'http://www.portalfiscal.inf.br/cte'}

    # Caminhos principais
    infCte = root.find('.//cte:infCte', ns)
    emit = infCte.find('.//cte:emit', ns)
    dest = infCte.find('.//cte:dest', ns)
    ide = infCte.find('.//cte:ide', ns)
    vPrest = infCte.find('.//cte:vPrest', ns)
    compl = infCte.find('.//cte:compl', ns)
    infModal = infCte.find('.//cte:infModal', ns)
    rodo = infModal.find('.//cte:rodo', ns) if infModal is not None else None

    # Chave de acesso
    chave_acesso = infCte.attrib.get('Id', '')
    if chave_acesso.startswith('CTe'):
        chave_acesso = chave_acesso[3:]

    numero_cte = ide.findtext('cte:nCT', default='', namespaces=ns)

    # Emitente
    cnpj_emitente = emit.findtext('cte:CNPJ', default='', namespaces=ns)
    nome_emitente = emit.findtext('cte:xNome', default='', namespaces=ns)

    # Destinatário
    cnpj_destinatario = dest.findtext('cte:CNPJ', default='', namespaces=ns)
    nome_destinatario = dest.findtext('cte:xNome', default='', namespaces=ns)

    # Valor total
    valor_total = vPrest.findtext('cte:vTPrest', default='0', namespaces=ns)
    valor_total = float(valor_total.replace(',', '.'))

    # Data de emissão
    data_emissao = ide.findtext('cte:dhEmi', default='', namespaces=ns)
    if data_emissao:
        data_emissao = data_emissao.split('T')[0]
        data_emissao = datetime.strptime(data_emissao, '%Y-%m-%d')
    else:
        data_emissao = datetime.now()

    # Origem e destino
    municipio_inicio = ide.findtext('cte:xMunIni', default='', namespaces=ns)
    uf_inicio = ide.findtext('cte:UFIni', default='', namespaces=ns)
    municipio_destino = ide.findtext('cte:xMunFim', default='', namespaces=ns)
    uf_destino = ide.findtext('cte:UFFim', default='', namespaces=ns)

    # Placa e motorista
    placa = ''
    motorista = ''
    if compl is not None:
        xObs = compl.findtext('cte:xObs', default='', namespaces=ns)
        if xObs:
            import re
            placa_match = re.search(r'PLACA ([A-Z0-9])', xObs)
            if placa_match:
                placa = placa_match.group(1)
            motorista_match = re.search(r'MOTORISTA ([A-Z .A-Z]+), CPF', xObs)
            if motorista_match:
                motorista = motorista_match.group(1)
    # fallback para placa no modal rodo
    if not placa and rodo is not None:
        placa = rodo.findtext('cte:placa', default='', namespaces=ns)
    # fallback para motorista (nome pode estar no xObs)
    if not motorista and compl is not None and xObs:
        import re
        motorista_match = re.search(r'MOTORISTA ([A-Z .A-Z]+), CPF', xObs)
        if motorista_match:
            motorista = motorista_match.group(1)

    dados_adicionais = {
        'municipio_inicio': municipio_inicio,
        'uf_inicio': uf_inicio,
        'municipio_destino': municipio_destino,
        'uf_destino': uf_destino,
        'placa': placa,
        'motorista': motorista
    }

    return {
        'chave_acesso': chave_acesso,
        'numero_cte': numero_cte,
        'cnpj_emitente': cnpj_emitente,
        'nome_emitente': nome_emitente,
        'cnpj_destinatario': cnpj_destinatario,
        'nome_destinatario': nome_destinatario,
        'valor_total': valor_total,
        'data_emissao': data_emissao,
        'dados_adicionais': dados_adicionais
    }




if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Importa um CT-e XML para o banco de dados.')
    parser.add_argument('xml_path', help='Caminho do arquivo XML do CT-e')
    args = parser.parse_args()
    importar_cte(args.xml_path) 