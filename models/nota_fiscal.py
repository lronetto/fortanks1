from models.database import db
from models.unidade import Unidade
from datetime import datetime
from flask import render_template, current_app
from io import BytesIO
import tempfile
import requests
from dotenv import load_dotenv
import os
import json
from flask_login import current_user
from models.conversao_unidade import comparar_unidades
from flask import Response
import base64
from utils.gerar_pdf import gerar_pdf_danfe
import xml.etree.ElementTree as ET
from decimal import Decimal
import logging
from models.upload import Upload
from models.arquivei import Arquivei
from models.logs import Logs
import xmltodict
logger = logging.getLogger(__name__)
load_dotenv()
ARQUIVEI_API_ID = os.getenv('ARQUIVEI_API_ID')
ARQUIVEI_API_KEY = os.getenv('ARQUIVEI_API_KEY')

CNPJS_FILIAIS = ['27126997000349','27126997000268','27126997000420']
CNPJS_MATRIZ = ['27126997000187']
CNPJS_MATRIZ_FILIAIS = CNPJS_MATRIZ + CNPJS_FILIAIS
CFOPS_COMPRA = [6101,5101,5405,6105,6401]
CFOPS_VENDA = [6101,5101,6107]
CFOPS_TRANSFERENCIA = [5949,6949]

def get_xml_text(element, xpath, ns):
    """
    Função auxiliar para obter texto de um elemento XML, retornando None se o elemento não existir
    """
    if element is None:
        return None
    
    try:
        found = element.find(xpath, ns)
        return found.text if found is not None else None
    except:
        return None
class NotaFiscal(db.Model):
    """
    Modelo para representar Notas Fiscais
    """
    __tablename__ = 'nf_notas'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Integer, nullable=False)
    numero_nf = db.Column(db.String(20), nullable=False)
    chave_acesso = db.Column(db.String(44), unique=True, nullable=False)
    data_emissao = db.Column(db.DateTime, nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Dados do emitente e destinatário
    cnpj_emitente = db.Column(db.String(14), nullable=False)
    nome_emitente = db.Column(db.String(100), nullable=False)
    cnpj_destinatario = db.Column(db.String(14), nullable=False)
    nome_destinatario = db.Column(db.String(100), nullable=False)
    
    # Dados de processamento
    xml_data = db.Column(db.Text, nullable=True)
    status_processamento = db.Column(db.String(20), default='importado', nullable=False)
    #solicitacao_id = db.Column(db.Integer, db.ForeignKey('solicitacoes.id'), nullable=True)
    
    # Datas de controle
    data_importacao = db.Column(db.DateTime, default=datetime.now, nullable=False)
    #data_cadastro = db.Column(db.DateTime, default=datetime.now)
    data_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    dados_adicionais = db.Column(db.Text, nullable=True)
    
    # Relacionamentos
    itens = db.relationship('NotaFiscalItem', backref='nota_fiscal', cascade='all, delete-orphan')

    upload = None
    cancelada = False
    pdf = None
    inserido = False
    
    def __init__(self, xml_data=None, chave_acesso=None, id=None, cancelada=False,tipo=None):
        self.xml_data = xml_data
        self.chave_acesso = chave_acesso
        self.id = id
        self.upload = None
        self.cancelada = cancelada
        if xml_data and tipo is None:
            self.tipo = self.extrair_tipo_nota(xml_data)
            if self.tipo is 'nfe':
                self.processar_nf()
            elif self.tipo is 'cte':
                self.processar_cte()
            
        if xml_data and tipo == 'nfe':
            print(f'NotaFiscal xml')
            self.processar_nf()
            
                
        if xml_data and tipo == 'cte':
            print(f'NotaFiscal cte')
            return  self.processar_cte()
            
        if chave_acesso:
            nota = NotaFiscal.query.filter(NotaFiscal.chave_acesso==chave_acesso).first()
            if nota:
                for key, value in nota.__dict__.items():
                    setattr(self, key, value)
                
        if id:
            nota = NotaFiscal.query.get_or_404(id)
            if nota:
                for key, value in nota.__dict__.items():
                    setattr(self, key, value)
                    
                upload = Upload.query.filter_by(pai='NotaFiscal', pai_id=self.id, tipo=1).first()
                if not upload:
                    pdf_data = Arquivei(chave_acesso=self.chave_acesso)
                    #print(f'pdf_data: {pdf_data}')
                    print(f'id: {self.id} chave: {self.chave_acesso}')
                    self.upload = Upload('NotaFiscal', self.id, 1, filename=f'{self.chave_acesso}.pdf', mimetype='application/pdf', blob=pdf_data.pdf)
                else:
                    self.upload = upload
                print('self.upload: ',self.upload)

    def extrair_tipo_nota(self, xml_data):
        """
        Extrai o tipo de nota fiscal do XML
        """
        root = ET.fromstring(base64.b64decode(xml_data).decode('utf-8'))
        ns = {'cte': 'http://www.portalfiscal.inf.br/cte'}
        ns1 = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        infCte = root.find('.//cte:infCte', ns) or root.find('.//infCte', ns)
        infNFe = root.find('.//nfe:infNFe', ns1) or root.find('.//infNFe', ns)
        if infNFe:
            return 'nfe'

        if infCte:
            return 'cte'
        else:
            return None
    def save(self):
        """
        Salva a nota fiscal no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove a nota fiscal do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    
    def todos_itens_importados(self):
        """
        Verifica se todos os itens da nota fiscal foram importados para o estoque
        
        Returns:
            bool: True se todos os itens foram importados, False caso contrário
        """
        if not self.itens:
            return False
            
        for item in self.itens:
            if not item.importado_estoque:
                return False
                
        return True
    
    def percentual_importacao(self):
        """
        Calcula o percentual de itens da nota fiscal que foram importados para o estoque
        
        Returns:
            float: Percentual de itens importados (0 a 100)
        """
        if not self.itens:
            return 0
            
        total_itens = len(self.itens)
        itens_importados = sum(1 for item in self.itens if item.importado_estoque)
        
        return (itens_importados / total_itens) * 100
    
    def get_pdf(self):
        if not self.upload:
            if not db.session.query(Upload.id).filter_by(pai='NotaFiscal', pai_id=self.id, tipo=1).first():
                pdf_data = Arquivei(chave_acesso=self.chave_acesso)
                self.upload = Upload(pai='NotaFiscal', pai_id=self.id, tipo=1, filename=f'{self.chave_acesso}.pdf', mimetype='application/pdf', blob=pdf_data.pdf)
        return self.upload
    def get_chave_acesso(self):
        return self.chave_acesso
    
    def get_xml_json(self):
        dictvar  = xmltodict.parse(base64.b64decode(self.xml_data).decode('utf-8'))
        return dictvar

    def importar_arquivei(data_inicial,data_final,tipo='nfe'):
        notas = Arquivei(data_inicial=data_inicial, data_final=data_final,tipo=tipo)
        total = len(notas.xml_datas)
        i=0
        existente=0
        if total > 0:
            
            for xml_data in notas.xml_datas:
                nf = NotaFiscal(xml_data=xml_data,tipo=tipo)
                existente+=(1 if nf.inserido else 0)
                i+=1
        log = {
            'data_ini': data_inicial,
            'data_fim': data_final,
            'total': total,
            'existentes': existente,
            'tipo': tipo
        }
        Logs(local='importar_arquivei', data=datetime.now(), texto=json.dumps(log))
        
    def processar_cte(self):
        chave_acesso, dados = self.extrair_dados_xml_cte()
        #print(f'dados: {dados}')
        # Verifica se já existe
        existente = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
        if existente:
            
            existente.dados_adicionais = json.dumps(dados.get('dados_adicionais'), ensure_ascii=False)
            existente.save()
            existente.inserido = False
            return existente
        try:
            self.tipo = 2
            self.numero_nf = dados.get('numero_cte')
            self.chave_acesso = dados.get('chave_acesso')
            self.data_emissao = dados.get('data_emissao')
            self.valor_total = dados.get('valor_total')
            self.cnpj_emitente = dados.get('cnpj_emitente')
            self.nome_emitente = dados.get('nome_emitente')
            self.cnpj_destinatario = dados.get('cnpj_destinatario')
            self.nome_destinatario = dados.get('nome_destinatario')
            self.status_processamento = 'importado'
            self.dados_adicionais = json.dumps(dados.get('dados_adicionais'), ensure_ascii=False)
            self.save()
            self.inserido = True
        except Exception as e:
            logger.error(f"Erro ao processar CT-e: {str(e)}")
            return False
        return self
    def processar_nf(self):
        """
        Cria e salva uma nota fiscal e seus itens a partir dos dados extraídos do XML.
        """
        try:
            # Extrair dados do XML
            #self.xml_data = base64.b64encode(xml_text.encode('utf-8')).decode('utf-8')
            #print('processando nota fiscal xml')
            chave_acesso, dados_nf = self.extrair_dados_xml_nfe()
            #print('chave_acesso: ',chave_acesso)
            #print('dados_nf: ',dados_nf)
            if not chave_acesso or not dados_nf:
                logger.warning(f"Não foi possível extrair dados do XML")
                return False
            self.chave_acesso=chave_acesso
            # Verificar se a nota fiscal já existe
            nf = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
            #print('nf: ',nf)
            #print('self: ',self)
            if nf:
                Logs(local='processar_nf',data=datetime.now(),texto=f"Nota {chave_acesso} já existe no banco de dados")
                logger.info(f"Nota {chave_acesso} já existe no banco de dados")
                nf.inserido = False
                print(f'num ={nf.numero_nf} dados_adicionais: {nf.dados_adicionais}')
                if not nf.dados_adicionais:
                   # print(f'num ={nf.numero_nf} dados_adicionais: {nf.dados_adicionais}')
                    nf.dados_adicionais = json.dumps(dados_nf.get('dados_adicionais'), ensure_ascii=False)
                    nf.save()
                
                return nf
            
            #self.xml_data=self.xml_data
            self.numero_nf=dados_nf.get('numero')
            self.tipo=dados_nf.get('tipo')
            self.chave_acesso=chave_acesso
            self.data_emissao=dados_nf.get('data_emissao')
            self.valor_total=dados_nf.get('valor_total')
            self.cnpj_emitente=dados_nf.get('cnpj_emitente')
            self.nome_emitente=dados_nf.get('nome_emitente')
            self.cnpj_destinatario=dados_nf.get('cnpj_destinatario')
            self.nome_destinatario=dados_nf.get('nome_destinatario')
            self.status_processamento='importado'
            self.dados_adicionais = json.dumps(dados_nf.get('dados_adicionais'), ensure_ascii=False)

            self.save()
            for item_nf in dados_nf.get('itens', []):
                item_fiscal = NotaFiscalItem(
                    nf_id=self.id,
                    codigo=item_nf.get('codigo'),
                    descricao=item_nf.get('descricao'),
                    quantidade=item_nf.get('quantidade'),
                    valor_unitario=item_nf.get('valor_unitario'),
                    valor_total=item_nf.get('valor_total'),
                    ncm=item_nf.get('ncm'),
                    cfop=item_nf.get('cfop'),
                    unidade=item_nf.get('unidade'),
                    dados_adicionais=json.dumps(item_nf.get('dados_adicionais'), ensure_ascii=False)

                )
                item_fiscal.save()
            self.vincular_automaticamente()
            db.session.refresh(self)
            if not (self.cnpj_emitente in CNPJS_MATRIZ_FILIAIS):
                print(f'importando itens para estoque')
                self.importar_itens_para_estoque()
            

            self.inserido = True
            return self

        except Exception as e:
            logger.error(f"Erro ao processar nota fiscal: {str(e)}")
            return False
    def extrair_dados_xml_cte(self):

        root = ET.fromstring(base64.b64decode(self.xml_data).decode('utf-8'))
        ns = {'cte': 'http://www.portalfiscal.inf.br/cte'}

        # Caminhos principais
        infCte = root.find('.//cte:infCte', ns) or root.find('.//infCte', ns)
        emit = infCte.find('.//cte:emit', ns) or infCte.find('.//emit', ns)
        dest = infCte.find('.//cte:dest', ns) or infCte.find('.//dest', ns)
        rem = infCte.find('.//cte:rem', ns) or infCte.find('.//rem', ns)
        ide = infCte.find('.//cte:ide', ns) or infCte.find('.//ide', ns)
        vPrest = infCte.find('.//cte:vPrest', ns) or infCte.find('.//vPrest', ns)
        compl = infCte.find('.//cte:compl', ns) or infCte.find('.//compl', ns)
        imp = infCte.find('.//cte:imp', ns) or infCte.find('.//imp', ns)
        impostos = {}
        if imp is not None:
            ICMSa = imp.find('.//cte:ICMS', ns) or imp.find('.//ICMS', ns) or imp.find('.//ICMS00', ns) or imp.find('.//ICMS', ns)
            if ICMSa is not None:
                ICMSOutraUF = ICMSa.find('.//cte:ICMSOutraUF', ns)
                if ICMSOutraUF is not None:
                    CSTv = ICMSOutraUF.findtext('.//cte:CST', default='0', namespaces=ns)
                    vBCOutraUF = ICMSOutraUF.findtext('.//cte:vBCOutraUF', default='0', namespaces=ns)
                    pICMSOutraUF = ICMSOutraUF.findtext('.//cte:pICMSOutraUF', default='0', namespaces=ns)
                    vICMSOutraUF = ICMSOutraUF.findtext('.//cte:vICMSOutraUF', default='0', namespaces=ns)
                    impostos = {
                        'CST': CSTv,
                        'vBC': vBCOutraUF,
                        'pICMS': pICMSOutraUF,
                        'vICMS': vICMSOutraUF
                    }
                ICMS00 = ICMSa.find('.//cte:ICMS00', ns) or ICMSa.find('.//ICMS00', ns)
                if ICMS00 is not None:
                    CSTv = ICMS00.findtext('.//cte:CST', default='0', namespaces=ns)
                    vBC = ICMS00.findtext('.//cte:vBC', default='0', namespaces=ns)
                    pICMS = ICMS00.findtext('.//cte:pICMS', default='0', namespaces=ns)
                    vICMS = ICMS00.findtext('.//cte:vICMS', default='0', namespaces=ns)
                    impostos = {
                        'CST': CSTv,
                        'vBC': vBC,
                        'pICMS': pICMS,
                        'vICMS': vICMS
                    }
        infModal = infCte.find('.//cte:infModal', ns) or infCte.find('.//infModal', ns)
        rodo = infModal.find('.//cte:rodo', ns) if infModal is not None else None

        # Chave de acesso
        chave_acesso = infCte.attrib.get('Id', '') or infCte.attrib.get('id', '')
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
            'remetente': {
                'nome': rem.findtext('cte:xNome', default='', namespaces=ns),
                'cnpj': rem.findtext('cte:CNPJ', default='', namespaces=ns),
                'endereco': rem.findtext('cte:xLgr', default='', namespaces=ns),
                'municipio': rem.findtext('cte:xMun', default='', namespaces=ns),
                'uf': rem.findtext('cte:UF', default='', namespaces=ns)
            },
            'municipio_inicio': municipio_inicio,
            'uf_inicio': uf_inicio,
            'municipio_destino': municipio_destino,
            'uf_destino': uf_destino,
            'placa': placa,
            'motorista': motorista
        }
        dados_nf = {
            'chave_acesso': chave_acesso,
            'numero_cte': numero_cte,
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente,
            'cnpj_destinatario': cnpj_destinatario,
            'nome_destinatario': nome_destinatario,
            'valor_total': valor_total,
            'data_emissao': data_emissao,
            'dados_adicionais': dados_adicionais,
            'impostos': impostos,
            'tipo': 2
        }
        return chave_acesso, dados_nf     
    def extrair_dados_xml_nfe(self):
        """
        Extrai os dados de uma nota fiscal a partir do XML
        Retorna a chave de acesso e um dicionário com os dados da nota fiscal
        """
        try:
            # Parse do XML
            root = ET.fromstring(base64.b64decode(self.xml_data).decode('utf-8'))
            
            # Definir os namespaces
            ns = {
                'nfe': 'http://www.portalfiscal.inf.br/nfe'
            }
            
            # Extrair dados da nota
            inf_nfe = root.find('.//nfe:infNFe', ns) or root.find('.//infNFe', ns)
            if inf_nfe is None:
                # Tentar com outro namespace
                ns = {'': 'http://www.portalfiscal.inf.br/nfe'}
                inf_nfe = root.find('.//infNFe', ns)
                if inf_nfe is None:
                    logger.error("Não foi possível encontrar os dados da nota fiscal no XML")
                    return None, None
            
            # Extrair a chave de acesso
            chave_acesso = inf_nfe.attrib.get('Id', '')
            if chave_acesso.startswith('NFe'):
                chave_acesso = chave_acesso[3:]  # Remove o prefixo 'NFe'
            
            # Extrair dados essenciais
            ide = inf_nfe.find('.//nfe:ide', ns) or inf_nfe.find('.//ide', ns)
            emit = inf_nfe.find('.//nfe:emit', ns) or inf_nfe.find('.//emit', ns)
            dest = inf_nfe.find('.//nfe:dest', ns) or inf_nfe.find('.//dest', ns)
            total = inf_nfe.find('.//nfe:total/nfe:ICMSTot', ns) or inf_nfe.find('.//total/ICMSTot', ns)
            itens = inf_nfe.findall('.//nfe:det', ns) or inf_nfe.findall('.//det', ns)
            cobr = inf_nfe.find('.//nfe:cobr', ns) or inf_nfe.find('.//cobr', ns)
            total = inf_nfe.find('.//nfe:total', ns) or inf_nfe.find('.//total', ns)
            ICMSTot = total.find('.//nfe:ICMSTot', ns) or total.find('.//ICMSTot', ns)
            vIPI = ICMSTot.findtext('.//nfe:vIPI', default='0', namespaces=ns) or ICMSTot.findtext('.//vIPI', default='0', namespaces=ns)
            vPIS = ICMSTot.findtext('.//nfe:vPIS', default='0', namespaces=ns) or ICMSTot.findtext('.//vPIS', default='0', namespaces=ns)
            vCOFINS = ICMSTot.findtext('.//nfe:vCOFINS', default='0', namespaces=ns) or ICMSTot.findtext('.//vCOFINS', default='0', namespaces=ns)
            vICMS = ICMSTot.findtext('.//nfe:vICMS', default='0', namespaces=ns) or ICMSTot.findtext('.//vICMS', default='0', namespaces=ns)

            impostos = {
                'vIPI': vIPI,
                'vPIS': vPIS,
                'vCOFINS': vCOFINS,
                'vICMS': vICMS,
            }
            if cobr:
                fatura = cobr.find('.//nfe:fat', ns) or cobr.find('.//fat', ns)
                dup = fatura.find('.//nfe:dup', ns) or fatura.find('.//dup', ns)

            if not ide or not emit or not dest or not total:
                logger.error("Dados essenciais ausentes no XML da NFe")
                return chave_acesso, None
            
            # Extrair número da nota
            numero = get_xml_text(ide, './/nfe:nNF', ns) or get_xml_text(ide, './/nNF', ns)
            tipo = get_xml_text(ide, './/nfe:tpNF', ns) or get_xml_text(ide, './/tpNF', ns)
            # Extrair data de emissão
            data_emissao_text = get_xml_text(ide, './/nfe:dhEmi', ns) or get_xml_text(ide, './/dhEmi', ns) or get_xml_text(ide, './/dEmi', ns)
            if not data_emissao_text:
                logger.error("Data de emissão não encontrada no XML")
                return chave_acesso, None
                
            # Ajustar formato da data
            if 'T' in data_emissao_text:
                data_emissao = data_emissao_text.split('T')[0]
            else:
                data_emissao = data_emissao_text
            
            # Extrair CNPJ emitente
            cnpj_emitente = get_xml_text(emit, './/nfe:CNPJ', ns) or get_xml_text(emit, './/CNPJ', ns)
            nome_emitente = get_xml_text(emit, './/nfe:xNome', ns) or get_xml_text(emit, './/xNome', ns)
            
            # Extrair CNPJ destinatário
            cnpj_destinatario = get_xml_text(dest, './/nfe:CNPJ', ns) or get_xml_text(dest, './/CNPJ', ns) or ''
            if not cnpj_destinatario:
                # Tentar CPF
                cnpj_destinatario = get_xml_text(dest, './/nfe:CPF', ns) or get_xml_text(dest, './/CPF', ns) or ''
                
            nome_destinatario = get_xml_text(dest, './/nfe:xNome', ns) or get_xml_text(dest, './/xNome', ns) or 'Consumidor'
            
            # Extrair valor total
            valor_total_text = get_xml_text(total, './/nfe:vNF', ns) or get_xml_text(total, './/vNF', ns)
            if not valor_total_text:
                logger.error("Valor total não encontrado no XML")
                return chave_acesso, None
                
            valor_total = Decimal(valor_total_text)
            
            # Dados básicos da nota
            nfe_data = {
                'numero': numero,
                'tipo': tipo,
                'data_emissao': data_emissao,
                'cnpj_emitente': cnpj_emitente,
                'nome_emitente': nome_emitente,
                'cnpj_destinatario': cnpj_destinatario,
                'nome_destinatario': nome_destinatario,
                'valor_total': valor_total,
                'itens': [],
                'dados_adicionais': {},
                'impostos': impostos
            }
            
            # Extrair dados dos itens
            for item in itens:
                try:
                    num_item = item.attrib.get('nItem', '0')
                    prod = item.find('.//nfe:prod', ns) or item.find('.//prod', ns)

                    infAdProd = item.find('.//nfe:infAdProd', ns) or item.find('.//infAdProd', ns)
                    
                    if not prod:
                        logger.warning(f"Produto não encontrado para o item {num_item}")
                        continue
                    
                    codigo = get_xml_text(prod, './/nfe:cProd', ns) or get_xml_text(prod, './/cProd', ns) or ''
                    descricao = get_xml_text(prod, './/nfe:xProd', ns) or get_xml_text(prod, './/xProd', ns) or 'Sem descrição'
                    
                    quantidade_text = get_xml_text(prod, './/nfe:qCom', ns) or get_xml_text(prod, './/qCom', ns) or '0'
                    valor_unitario_text = get_xml_text(prod, './/nfe:vUnCom', ns) or get_xml_text(prod, './/vUnCom', ns) or '0'
                    valor_total_item_text = get_xml_text(prod, './/nfe:vProd', ns) or get_xml_text(prod, './/vProd', ns) or '0'
                    
                    ncm = get_xml_text(prod, './/nfe:NCM', ns) or get_xml_text(prod, './/NCM', ns) or ''
                    cfop = get_xml_text(prod, './/nfe:CFOP', ns) or get_xml_text(prod, './/CFOP', ns) or ''
                    unidade = get_xml_text(prod, './/nfe:uCom', ns) or get_xml_text(prod, './/uCom', ns) or 'UN'
                    
                    item_data = {
                        'codigo': codigo,
                        'descricao': descricao,
                        'quantidade': Decimal(quantidade_text),
                        'valor_unitario': Decimal(valor_unitario_text),
                        'valor_total': Decimal(valor_total_item_text),
                        'ncm': ncm,
                        'cfop': cfop,
                        'unidade': unidade,
                        'dados_adicionais':{
                            'infAdProd': infAdProd
                            }
                        }
                    
                    nfe_data['itens'].append(item_data)
                except Exception as e:
                    logger.error(f"Erro ao processar item {num_item}: {str(e)}")
            if cobr and dup:
                vencimento = dup.findtext('.//nfe:dVenc', ns) or dup.findtext('.//dVenc', ns)
                if vencimento:
                    vencimento = datetime.strptime(vencimento, '%Y-%m-%d')
                else:
                    vencimento = None
                if fatura:
                    numero_fatura = fatura.findtext('.//nfe:nFat', ns) or fatura.findtext('.//nFat', ns)
                    valor_total = fatura.findtext('.//nfe:vOrig', ns) or fatura.findtext('.//vOrig', ns)
                    valor_total = Decimal(valor_total)
                    nfe_data['dados_adicionais']['fatura'] = {
                        'vencimento': vencimento,
                        'numero_fatura': numero_fatura,
                        'valor_total': valor_total
                    }

            return chave_acesso, nfe_data
        
        except Exception as e:
            logger.error(f"Erro ao extrair dados do XML: {str(e)}")
            return None, None
    def vincular_automaticamente(self):
        """
        Tenta vincular automaticamente materiais a todos os itens de uma nota fiscal
        com base em vinculações anteriores e importa para o estoque se o material já estiver vinculado
        
        Args:
            nota_fiscal_id: ID da nota fiscal
        """
            # Para cada item sem material vinculado, tentar buscar um material
        itens_vinculados = 0
        for item in self.itens:
            if not item.material_id:
                # Buscar item com base em vinculações anteriores
                item_anterior = item.buscar_material_vinculado_anteriormente()
                
                # Se encontrar, vincular
                if item_anterior:
                    print(f'item_anterior: {item_anterior.unidade} {item.unidade}')
                    if comparar_unidades(item.unidade, item_anterior.unidade):
                        print(f'fator_conversao: {item_anterior.fator_conversao_aplicado}')
                        fator_conversao = item_anterior.fator_conversao_aplicado
                        if fator_conversao:
                            item.fator_conversao_aplicado = fator_conversao
                            itens_vinculados += 1
                            item.material_id = item_anterior.material_id
                        else:
                            item.fator_conversao_aplicado = fator_conversao
                            itens_vinculados += 1
                        item.save()
        log={
            "itens": len(self.itens),
            "itens_vinculados": itens_vinculados
        }
        Logs("vinculacao_automatica",datetime.now(),json.dumps(log))
        print(f'itens_vinculados: {itens_vinculados}')
        return itens_vinculados
    def importar_itens_para_estoque(self):
        for item in self.itens:
            item.importar_para_estoque()
    def to_dict(self):
        return {
            'id': self.id,
            'numero_nf': self.numero_nf,
            'chave_acesso': self.chave_acesso,
            'data_emissao': self.data_emissao,
            'valor_total': self.valor_total,
        }

class NotaFiscalItem(db.Model):
    """
    Modelo para representar itens de Nota Fiscal
    """
    __tablename__ = 'nf_itens'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(60), nullable=True)
    descricao = db.Column(db.String(255), nullable=False)
    quantidade = db.Column(db.Numeric(15, 4), nullable=False)
    valor_unitario = db.Column(db.Numeric(15, 4), nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Dados fiscais
    ncm = db.Column(db.String(8), nullable=True)
    cfop = db.Column(db.String(4), nullable=True)
    unidade = db.Column(db.String(6), nullable=True)
    
    # Campos para conversão de unidades
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidades.id'), nullable=True)
    unidade_rel = db.relationship('Unidade', backref='nf_itens', lazy=True)
    unidade_original = db.Column(db.String(6), nullable=True)
    quantidade_original = db.Column(db.Numeric(15, 4), nullable=True)
    fator_conversao_aplicado = db.Column(db.Numeric(15, 4), nullable=True)
    
    # Vinculação com material do sistema
    material_id = db.Column(db.Integer, db.ForeignKey('materiais.id'), nullable=True)
    material = db.relationship('Material', backref='itens_nota_fiscal')

    movimentacao_estoque_id = db.Column(db.Integer, nullable=True)
    

    
    # Status de importação para estoque
    importado_estoque = db.Column(db.Boolean, default=False)
    data_importacao_estoque = db.Column(db.DateTime, nullable=True)
    usuario_importacao_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    usuario_importacao = db.relationship('Usuario', foreign_keys=[usuario_importacao_id])
    
    # Campos para tracking de importação
    tentativas_importacao = db.Column(db.Integer, default=0)
    ultima_tentativa_importacao = db.Column(db.DateTime, nullable=True)
    status_importacao = db.Column(db.String(30), default='Pendente')
    dados_adicionais = db.Column(db.Text, nullable=True)
    
    # Chave estrangeira
    nf_id = db.Column(db.Integer, db.ForeignKey('nf_notas.id', ondelete='CASCADE'), nullable=False)
    # Datas de controle
    data_criacao = db.Column(db.DateTime, default=datetime.now)
    data_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def save(self):
        """
        Salva o item de nota fiscal no banco de dados
        """
        db.session.add(self)
        db.session.commit()
    
    def delete(self):
        """
        Remove o item de nota fiscal do banco de dados
        """
        db.session.delete(self)
        db.session.commit()
    def buscar_material_vinculado_anteriormente(self):
        """
        Busca por um material que já foi vinculado anteriormente a um item com o mesmo código ou descrição
        
        Args:
            codigo: Código do item na nota fiscal
            descricao: Descrição do item na nota fiscal
            
        Returns:
            int: ID do material vinculado ou None se não encontrado
        """
        try:
            # Prioridade 1: Buscar a primeira vinculacao
            if self.codigo:
                item_anterior = NotaFiscalItem.query.join(NotaFiscal, NotaFiscalItem.nf_id == NotaFiscal.id).filter(
                    NotaFiscalItem.codigo == self.codigo,
                    NotaFiscalItem.nota_fiscal.has(NotaFiscal.cnpj_emitente == self.nota_fiscal.cnpj_emitente),
                    NotaFiscalItem.material_id.isnot(None),
                    NotaFiscalItem.importado_estoque == True
                ).order_by(NotaFiscalItem.data_importacao_estoque.asc()).first()
                
                if item_anterior and item_anterior.material_id:
                    return item_anterior
            
            # Prioridade 2: Buscar por correspondência exata na descrição
            if self.descricao:
                item_anterior = NotaFiscalItem.query.filter(
                    NotaFiscalItem.descricao == self.descricao,
                    NotaFiscalItem.material_id.isnot(None),
                    NotaFiscalItem.importado_estoque == True
                ).order_by(NotaFiscalItem.data_importacao_estoque.asc()).first()
                
                if item_anterior and item_anterior.material_id:
                    return item_anterior
                    
            return None
        except Exception as e:
            return None
    def vincular(self,fator_conversao_aplicado,material):
        self.fator_conversao_aplicado = fator_conversao_aplicado
        self.material_id = material
        self.save()
    def vincular_todos(self):
        inicio = datetime.now()
        itens = NotaFiscalItem.query.filter(NotaFiscalItem.codigo==self.codigo,
                                            NotaFiscalItem.descricao==self.descricao,
                                            NotaFiscalItem.unidade==self.unidade,
                                            NotaFiscalItem.material_id==None).all()
        print(f'itens a ser vinculados: {len(itens)}')
        for item in itens:
            item.vincular(self.fator_conversao_aplicado,self.material_id)
            item.save()
        fim = datetime.now()
        print(f'tempo de execucao vincular_todos: {fim - inicio}')
    def vincular_e_importar_estoque_todos(self):
        inicio = datetime.now()
        itens = NotaFiscalItem.query.filter(NotaFiscalItem.codigo==self.codigo,
                                            NotaFiscalItem.descricao==self.descricao,
                                            NotaFiscalItem.unidade==self.unidade,
                                            NotaFiscalItem.material_id==None).all()
        self.importar_para_estoque()
        print(f'itens a ser vinculados e importado estoque: {len(itens)}')
        for item in itens:
            item.vincular(self.fator_conversao_aplicado,self.material_id)
            item.save()
            nota=self.nota_fiscal
            if nota.tipo == 1:
                if nota.cnpj_emitente not in CNPJS_MATRIZ_FILIAIS and nota.cnpj_destinatario in CNPJS_MATRIZ:
                    local = "Estoque Matriz"
                    tipo_movimento = 'entrada'
                    item.importar_para_estoque(local=local,tipo_movimento=tipo_movimento)
                elif nota.cnpj_emitente not in CNPJS_MATRIZ_FILIAIS and nota.cnpj_destinatario in CNPJS_FILIAIS:
                    local = "Estoque Filial " + nota.cnpj_destinatario
                    tipo_movimento = 'entrada'
                    item.importar_para_estoque(local=local,tipo_movimento=tipo_movimento)
                elif nota.cnpj_emitente in CNPJS_MATRIZ and nota.cnpj_destinatario in CNPJS_FILIAIS:
                    local = "Estoque Matriz"
                    tipo_movimento = 'saida'
                    item.importar_para_estoque(local=local,tipo_movimento=tipo_movimento)
                    local = "Estoque Filial " + nota.cnpj_destinatario
                    tipo_movimento = 'entrada'
                    item.importar_para_estoque(local=local,tipo_movimento=tipo_movimento)
                elif nota.cnpj_emitente in CNPJS_FILIAIS and nota.cnpj_destinatario in CNPJS_MATRIZ:
                    local = "Estoque Filial" + nota.cnpj_destinatario
                    tipo_movimento = 'saida'
                    item.importar_para_estoque(local=local,tipo_movimento=tipo_movimento)
                    local = "Estoque Matriz"
                    tipo_movimento = 'entrada'
                    item.importar_para_estoque(local=local,tipo_movimento=tipo_movimento)
            
            return
            
        fim = datetime.now()
        print(f'tempo de execucao vincular_e_importar_estoque_todos: {fim - inicio}')
    def importar_para_estoque(self,usuario_id=None,centro_custo_id=None,observacao=None,local='Estoque Matriz',tipo_movimento='entrada'):
        """
        Importa o item da nota fiscal para o estoque
        
        Args:
            usuario_id: ID do usuário que está realizando a importação
            centro_custo_id: ID do centro de custo (opcional)
            observacao: Observação adicional para a movimentação
            
        Returns:
            tuple: (bool, str) - (Sucesso, Mensagem)
        """
        inicio = datetime.now()
        from models.estoque import Estoque, MovimentacaoEstoque
        
        # Verificar se o item já foi importado
        if self.importado_estoque:
            return (False, "Item já foi importado para o estoque.")
        
        # Verificar se o item tem um material vinculado
        if not self.material_id:
            return (False, "Este item não está vinculado a um material do sistema.")
        
        try:
            # Buscar estoque existente para o material
            estoque = Estoque.query.filter_by(material_id=self.material_id,localizacao=local).first()
            
            # Se não existe estoque para este material, criar um novo
            if not estoque:
                print(f"Criando novo estoque para o material {self.material_id}")


                estoque = Estoque(
                    material_id=self.material_id,
                    tipo_item='material',
                    quantidade=0,
                    localizacao=local,
                    centro_custo_id=centro_custo_id,
                    usuario_id=usuario_id
                )
                estoque.save()
                db.session.refresh(estoque)
            else:
                print(f"Estoque encontrado para o material {self.material_id}")
            # Criar movimentação de entrada no estoque
            if not observacao:
                observacao = f"Importação da NF {self.nota_fiscal.numero_nf} de {self.nota_fiscal.nome_emitente}"
                
            # Adicionar informação sobre conversão de unidade, se aplicável
            if self.fator_conversao_aplicado:
                self.quantidade = self.quantidade*self.fator_conversao_aplicado
                observacao += f" (Conversão: {self.quantidade} {self.unidade} → {self.quantidade} {estoque.material.unidade_obj.nome})"
            
            # Registrar a quantidade atual antes da atualização para log
            quantidade_anterior = float(estoque.quantidade) if estoque.quantidade else 0
            
            # Criar e salvar a movimentação
            movimentacao = MovimentacaoEstoque(
                estoque_id=estoque.id,
                tipo_movimento=tipo_movimento,
                quantidade=self.quantidade,
                data_movimento=self.nota_fiscal.data_emissao,
                nota_fiscal_item_id=self.id,
                origem_tipo='NotaFiscal',
                origem_id=self.nota_fiscal.id,
                observacao=observacao,
                usuario_id=current_user.id
            )
            
            # Salvar movimentação (isso vai atualizar o estoque automaticamente)
            movimentacao.save()
            
            
            # Garantir que o estoque seja atualizado corretamente
            
            
            # Verificar se a quantidade foi realmente atualizada
            quantidade_nova = float(estoque.quantidade) if estoque.quantidade else 0
            
            # Se a quantidade não foi atualizada, forçar a atualização diretamente
            if quantidade_nova <= quantidade_anterior:
                estoque.quantidade = quantidade_anterior + float(self.quantidade)
                estoque.save()
                quantidade_nova = float(estoque.quantidade)
            
            # Atualizar status do item
            self.importado_estoque = True
            self.data_importacao_estoque = datetime.now()
            self.usuario_importacao_id = usuario_id
            self.status_importacao = 'importado'
            self.ultima_tentativa_importacao = datetime.now()
            self.tentativas_importacao += 1
            self.movimentacao_estoque_id = movimentacao.id
            self.save()
            fim = datetime.now()
            print(f'tempo de execucao importar_para_estoque: {fim - inicio}')
            # Verificar se o material é da categoria EPI
            # Se for, criar automaticamente um registro de EPI para este material
            from models.epi import EPI
            if self.material and self.material.categoria == 'EPI':
                # Verificar se já existe um EPI para este material
                epi_existente = EPI.query.filter_by(material_id=self.material_id).first()
                
                if not epi_existente:
                    # Criar um novo registro de EPI
                    epi = EPI()
                    epi.material_id = self.material_id
                    epi.estoque_minimo = 1  # Valor padrão
                    epi.usuario_id = usuario_id
                    
                    # Salvar o EPI (não precisa adicionar estoque, pois já foi criado como material)
                    epi.save()
                    
                    # Adicionar mensagem sobre a criação do EPI
                    mensagem_extra = f" Material identificado como EPI. Registro de EPI criado automaticamente."
                    return (True, f"Item importado com sucesso. {self.quantidade} {self.unidade or ''} adicionado(s) ao estoque. Estoque anterior: {quantidade_anterior}, Estoque atual: {quantidade_nova}{mensagem_extra}")
            
            return (True, f"Item importado com sucesso. {self.quantidade} {self.unidade or ''} adicionado(s) ao estoque. Estoque anterior: {quantidade_anterior}, Estoque atual: {quantidade_nova}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # Registrar a tentativa
            self.ultima_tentativa_importacao = datetime.now()
            self.tentativas_importacao += 1
            self.status_importacao = 'Erro'
            self.dados_adicionais = str(e)
            self.save()
            
            return (False, f"Erro ao importar item para estoque: {str(e)}")
    
    def __repr__(self):
        """
        Representação em string do item de nota fiscal
        """
        return f'<NotaFiscalItem {self.id} - {self.descricao[:30]}>' 