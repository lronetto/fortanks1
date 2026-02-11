from models.database import db
from datetime import datetime
from flask import render_template, current_app
from io import BytesIO
import tempfile
import requests
from dotenv import load_dotenv
import os
import json
from flask_login import current_user
from flask import Response
import base64
from utils.gerar_pdf import gerar_pdf_danfe
import xml.etree.ElementTree as ET
from decimal import Decimal
import logging
from models.estoque import Estoque, EstoqueMovimentacoes
from models.epi import Epi
from models.upload import Upload
from models.arquivei import Arquivei
from models.logs import Logs
from models.unidade import UnidadesConversao, get_conversao_unidade, comparar_unidades,Unidades
import xmltodict
logger = logging.getLogger(__name__)
load_dotenv()
ARQUIVEI_API_ID = os.getenv('ARQUIVEI_API_ID')
ARQUIVEI_API_KEY = os.getenv('ARQUIVEI_API_KEY')

CNPJS_FILIAIS = ['27126997000349','27126997000268','27126997000420']
CNPJS_MATRIZ = ['27126997000187']
CNPJS_MATRIZ_FILIAIS = CNPJS_MATRIZ + CNPJS_FILIAIS
CFOPS_COMPRA = ['6101','5101','5405','6105','6401']
CFOPS_VENDA = ['6101','5101','6107']
CFOPS_TRANSFERENCIA = ['5949','6949']

def determinar_movimentacoes_estoque(nota_fiscal):
    """
    Determina as movimentações de estoque necessárias baseado nos CNPJs da nota fiscal.
    
    Args:
        nota_fiscal: Instância de NotaFiscal
        
    Returns:
        list: Lista de tuplas (local, tipo_movimento) que devem ser processadas
    """
    movimentacoes = []
    print("cnpj_emitente: ",nota_fiscal.cnpj_emitente)
    print("cnpj_destinatario: ",nota_fiscal.cnpj_destinatario)
    # Apenas processar notas fiscais (tipo 1)
    if nota_fiscal.tipo >1:
        return movimentacoes
    
    cnpj_emitente = nota_fiscal.cnpj_emitente
    cnpj_destinatario = nota_fiscal.cnpj_destinatario
    
    # Caso 1: Compra externa para Matriz
    if cnpj_emitente not in CNPJS_MATRIZ_FILIAIS and cnpj_destinatario in CNPJS_MATRIZ:
        movimentacoes.append(("Estoque Matriz", "entrada"))
    
    # Caso 2: Compra externa para Filial
    elif cnpj_emitente not in CNPJS_MATRIZ_FILIAIS and cnpj_destinatario in CNPJS_FILIAIS:
        movimentacoes.append((f"Estoque Filial {cnpj_destinatario}", "entrada"))
    
    # Caso 3: Transferência Matriz -> Filial
    elif cnpj_emitente in CNPJS_MATRIZ and cnpj_destinatario in CNPJS_FILIAIS:
        movimentacoes.append(("Estoque Matriz", "saida"))
        movimentacoes.append((f"Estoque Filial {cnpj_destinatario}", "entrada"))
    
    # Caso 4: Transferência Filial -> Matriz
    elif cnpj_emitente in CNPJS_FILIAIS and cnpj_destinatario in CNPJS_MATRIZ:
        movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "saida"))
        movimentacoes.append(("Estoque Matriz", "entrada"))
    # Caso 5: Transferência interna para externa
    elif cnpj_emitente in CNPJS_MATRIZ_FILIAIS and cnpj_destinatario not in CNPJS_MATRIZ_FILIAIS:
        if cnpj_emitente in CNPJS_MATRIZ:
            if nota_fiscal.tipo == 1:
                movimentacoes.append(("Estoque Matriz", "saida"))
            else:
                movimentacoes.append(("Estoque Matriz", "entrada"))
        if cnpj_emitente in CNPJS_FILIAIS:
            if nota_fiscal.tipo == 1:
                movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "saida"))
            else:
                movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "entrada"))
    # Caso 6: Transferência matriz para matriz
    elif cnpj_emitente in CNPJS_MATRIZ and cnpj_destinatario in CNPJS_MATRIZ:
        if nota_fiscal.tipo == 1:
            movimentacoes.append((f"Estoque Matriz", "saida"))
        else:
            movimentacoes.append((f"Estoque Matriz", "entrada"))
    # Caso 7: Transferência filial para filial
    elif cnpj_emitente in CNPJS_FILIAIS and cnpj_destinatario in CNPJS_FILIAIS:
        if nota_fiscal.tipo == 1:
            movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "saida"))
        else:
            movimentacoes.append((f"Estoque Filial {cnpj_emitente}", "entrada"))
    return movimentacoes
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
#Nota Fiscal
#tipo 0 - NFe
#tipo 1 - NFe
#tipo 2 - CTE
#tipo 3 - NFSe
class NotaFiscal(db.Model):
    """
    Modelo para representar Notas Fiscais
    """
    __tablename__ = 'NotaFiscal'
    
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Integer, nullable=False)
    numero_nf = db.Column(db.String(20), nullable=False)
    chave_acesso = db.Column(db.String(100), unique=True, nullable=False)
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
    vencimento = db.Column(db.String(10), nullable=True)
    
    # Relacionamentos
    itens = db.relationship('NotaFiscalItem', backref='nota_fiscal', cascade='all, delete-orphan')

    upload = None
    cancelada = False
    pdf = None
    inserido = False
    existente = False
    logs = None
    data = None

    
    def __init__(self, data=None, xml_data=None,chave_acesso=None, id=None, cancelada=False,tipo=None):
       
        self.logs = {
            'erro': [],
            'mensagem': [],
            'existente': 0,
            'existentes': [],
            'inserido': 0,
            'inseridos': [],
            'importacao': [],
            'vinculacao': [],
        }
        self.data = data
        self.chave_acesso = chave_acesso
        self.id = id
        self.tipo = tipo
        self.upload = None
        self.cancelada = cancelada
        if data and not tipo:
            self.tipo = self.extrair_tipo_nota(data)
        if not xml_data:
            if self.data.get('xml',None):
                self.xml_data = self.data.get('xml',None)
                self.tipo = self.extrair_tipo_nota(self.data)
        else:
            self.xml_data = xml_data
            dicta = self.get_xml_json()
            print(f'dicta: {dicta}')
            if dicta.get('CompNfse') or dicta.get('tcListaNFse') or dicta.get('ListaNfse') or dicta.get('NFSe'):
                self.tipo = 'nfse'
            elif dicta.get('NFe'):
                self.tipo = 'nfe'
            elif dicta.get('CTe'):
                self.tipo = 'cte'
        print(f'self.tipo: {self.tipo}')
        if self.tipo:
            if self.tipo == 'nfe':
                self.processar_nfe()
            elif self.tipo == 'cte':
                self.processar_cte()
            elif self.tipo == 'nfse':
                self.processar_nfse()
             
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
    def extrair_tipo_nota(self, data):
        """
        Extrai o tipo de nota fiscal do XML
        """
        if data.get('id'):
            return 'nfse'
        if data.get('chave_acesso'):
            if int(data.get('chave_acesso')[20:22]) == 55:
                return 'nfe'
            elif int(data.get('chave_acesso')[20:22]) == 57:
                return 'cte'
            else:
                return 'nfse'
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
            print(f'get_pdf: {self.id} chave: {self.chave_acesso}')
            if not db.session.query(Upload.id).filter_by(pai='NotaFiscal', pai_id=self.id, tipo=1).first():
                up = Upload.query.filter_by(pai='NotaFiscal', filename=f'{self.chave_acesso}.pdf', tipo=1).first()
                if up:
                    up.pai_id = self.id
                    up.save()
                    self.upload = up
                else:
                    if self.dados_adicionais:
                        dados_json = json.loads(self.dados_adicionais) if isinstance(self.dados_adicionais, str) else self.dados_adicionais
                        if isinstance(dados_json, dict):
                            if dados_json.get('id'):
                                pdf_data = Arquivei(chave_acesso=dados_json.get('id'),pdf=True)
                            else:
                                pdf_data = Arquivei(chave_acesso=self.chave_acesso,pdf=True)
                    else:
                        pdf_data = Arquivei(chave_acesso=self.chave_acesso,pdf=True)
                    if pdf_data.pdf:
                        self.upload = Upload(pai='NotaFiscal', pai_id=self.id, tipo=1, filename=f'{self.chave_acesso}.pdf', mimetype='application/pdf', blob=pdf_data.pdf)
                    else:
                        return None
        return self.upload
    def get_chave_acesso(self):
        return self.chave_acesso    
    def get_xml_json(self):
        dictvar  = xmltodict.parse(base64.b64decode(self.xml_data).decode('utf-8'))
        return dictvar
    def get_vencimento(self):
        # Primeiro tentar obter do dados_adicionais (mais rápido, já está processado)
        if self.dados_adicionais:
            try:
                dados_json = json.loads(self.dados_adicionais) if isinstance(self.dados_adicionais, str) else self.dados_adicionais
                if isinstance(dados_json, dict):
                    fatura = dados_json.get('fatura', {})
                    if isinstance(fatura, dict):
                        vencimento_str = fatura.get('vencimento')
                        if vencimento_str:
                            return datetime.strptime(vencimento_str, '%Y-%m-%d')
            except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
                pass
        
        # Se não encontrou em dados_adicionais, tentar extrair do XML
        try:
            dictvar = self.get_xml_json()
            cobr = dictvar.get('nfeProc',{}).get('NFe',{}).get('infNFe',{}).get('cobr',{})
            if not cobr:
                return None
            
            dup = cobr.get('dup', None)
            if not dup:
                return None
            
            # Se dup é uma lista (múltiplas duplicatas), pegar a última (geralmente a mais importante)
            if isinstance(dup, list):
                if len(dup) > 0:
                    # Pegar a última duplicata (geralmente a mais importante)
                    dup = dup[-1]
                else:
                    return None
            
            # Se ainda for um dicionário, tentar obter o vencimento
            if isinstance(dup, dict):
                vencimento = dup.get('dVenc', None)
                if vencimento:
                    return datetime.strptime(vencimento, '%Y-%m-%d')
        except Exception:
            pass
        
        return None        
    def importar_arquivei(data_inicial,data_final,tipo='nfe',logs=None):
        notas = Arquivei(data_inicial=data_inicial, data_final=data_final,tipo=tipo)
        total = len(notas.datas)
        logs={
            'tipo': tipo,
            'total': 0,
            'existente': 0,
            'inserido': 0,
            'erro': [],
            'mensagem': [],
            'existentes': [],
            'inseridos': [],
        }
        logs['total'] = total
        i=0
        notasn = []
        if total > 0:
            for data in notas.datas:
                nf = NotaFiscal(data=data,tipo=tipo)
                if nf.logs['erro']:
                    logs['erro'].append(nf.logs['erro'])
                if nf.logs['mensagem']:
                    logs['mensagem'].append(nf.logs['mensagem'])
                if nf.logs['existentes']:
                    logs['existentes'].append(nf.logs)
                if nf.logs['inseridos']:
                    logs['inseridos'].append(nf.logs)
                notasn.append(nf)
            i+=1
        for nf in notasn:
            print(f'nf: {nf.id}')
            nf.get_pdf()
        print(f'logs: {logs}')
        return logs
    def processar_cte(self):
        chave_acesso, dados = self.extrair_dados_xml_cte()
        #print(f'dados: {dados}')
        # Verifica se já existe
        
        existente = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
        if existente:
            self.logs['existente'] += 1
            self.logs['existentes'].append({
                'numero_nf':existente.numero_nf,
                'tipo': 'cte',
                'valor_total': existente.valor_total,
                'cnpj_emitente': existente.cnpj_emitente,
                'nome_emitente': existente.nome_emitente,
                'cnpj_destinatario': existente.cnpj_destinatario,
                'nome_destinatario': existente.nome_destinatario,
                'dados_adicionais': existente.dados_adicionais,
            })
            existente.dados_adicionais = json.dumps(dados.get('dados_adicionais'), ensure_ascii=False)
            existente.save()
            return existente
        try:
            self.tipo = 2
            self.xml_data = self.data.get('xml',None)
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
            db.session.refresh(self)
            self.logs['inserido'] += 1
            self.logs['inseridos'].append(self.to_dict())

        except Exception as e:
            logger.error(f"Erro ao processar CT-e: {str(e)}")
            self.logs['erro'] = str(e)
            return False
    def processar_nfse(self):
        import traceback
        chave_acesso, dados = self.extrair_dados_xml_nfse()
        print(f'chave_acesso: {chave_acesso}')
        print(f'dados: {dados}')
        if not chave_acesso or not dados:
            logger.warning("processar_nfse: extração retornou chave ou dados vazios")
            return False

        try:
            existente = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
            if existente:
                #self.logs['existente'] += 1
                #self.logs['existentes'].append(existente.to_dict())
                existente.dados_adicionais = json.dumps(dados.get('dados_adicionais') or {}, ensure_ascii=False)
                existente.save()
                return existente
        except Exception as e:
            logger.error(f"processar_nfse [nota existente]: {e}", exc_info=True)
            #self.logs['erro'] = f"Ao atualizar nota existente: {str(e)}"
            return False

        dados_adicionais = dados.get('dados_adicionais') or {}
        try:
            if dados_adicionais.get('cancelada'):
                self.status_processamento = 'cancelada'
            else:
                self.status_processamento = 'importado'
            self.tipo = 3
            self.xml_data =base64.b64encode(self.xml_data.encode('utf-8')).decode('utf-8')
            self.numero_nf = dados.get('Numero')
            self.chave_acesso = chave_acesso
            self.data_emissao = dados.get('DataEmissao')
            self.valor_total = (dados.get('valores') or {}).get('ValorLiquidoNfse') or '0'
            self.cnpj_emitente = dados.get('cnpj_emitente')
            self.nome_emitente = dados.get('nome_emitente')
            self.cnpj_destinatario = dados.get('cnpj_destinatario')
            self.nome_destinatario = dados.get('nome_destinatario')
            self.dados_adicionais = json.dumps(dados_adicionais, ensure_ascii=False)
        except Exception as e:
            logger.error(f"processar_nfse [atribuir campos]: {e}", exc_info=True)
            #self.logs['erro'] = f"Ao atribuir campos da NFSe: {str(e)}\n{traceback.format_exc()}"
            return False

        try:
            self.save()
            db.session.refresh(self)
        except Exception as e:
            logger.error(f"processar_nfse [save/refresh]: {e}", exc_info=True)
            #self.logs['erro'] = f"Ao salvar NFSe no banco: {str(e)}\n{traceback.format_exc()}"
            return False

        try:
            pass
            #self.logs['inserido'] += 1
            #self.logs['inseridos'].append(self.to_dict())
        except Exception as e:
            logger.error(f"processar_nfse [to_dict/inserido]: {e}", exc_info=True)
            #self.logs['erro'] = f"Ao registrar log de inserção (to_dict): {str(e)}\n{traceback.format_exc()}"
            return False
    def processar_nfe(self):
        """
        Cria e salva uma nota fiscal e seus itens a partir dos dados extraídos do XML.
        """
        print(f'processar_nf: {self.id}')
        
        try:
            # Extrair dados do XML
            #self.xml_data = base64.b64encode(xml_text.encode('utf-8')).decode('utf-8')
            #print('processando nota fiscal xml')
            chave_acesso, dados_nf = self.extrair_dados_xml_nfe()
            #print('chave_acesso: ',chave_acesso)
            #print('dados_nf: ',dados_nf)
            if not chave_acesso or not dados_nf:
                logger.warning(f"Não foi possível extrair dados do XML")
                self.logs['erro'] = "Não foi possível extrair dados do XML"
                return False
            self.chave_acesso=chave_acesso
    
            
            # Verificar se a nota fiscal já existe
            nf = NotaFiscal.query.filter_by(chave_acesso=chave_acesso).first()
            #print('nf: ',nf)
            #print('self: ',self)
            
            if nf:
                self.logs['existente'] += 1
                self.logs['existentes'].append({
                    'numero_nf': nf.numero_nf,
                    'tipo': nf.tipo,
                    'valor_total': nf.valor_total,
                    'dados_adicionais': nf.dados_adicionais,
                })
                logger.info(f"Nota {chave_acesso} já existe no banco de dados")
                if not nf.dados_adicionais:
                    self.logs['mensagem'] = "Dados adicionais não encontrados adicionando"
                    nf.dados_adicionais = json.dumps(dados_nf.get('dados_adicionais'), ensure_ascii=False)
                    nf.save()
                return nf   
            
            self.xml_data=self.data.get('xml',None)
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
            db.session.commit()
            db.session.refresh(self)
            for item in self.itens:
                try:
                    sucesso, mensagem, estatisticas = item.vincular_e_importar_estoque_todos(
                        usuario_id=current_user.id if current_user else None,
                        centro_custo_id=None,
                        observacao= f"Importação da NF {self.numero_nf if self else 'N/A'}",
                    )
                    self.logs['vinculacao'].append(estatisticas['vinculacao'])
                    self.logs['importacao'].append(estatisticas['importacao'])
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    logger.error(f"Erro ao vincular e importar item {item.id}: {str(e)}")
                    self.logs['erro'].append(f'Erro ao vincular e importar item {item.id}: {str(e)}')

            self.logs['inserido'] += 1
            self.logs['inseridos'].append({
                'id': self.id,
                'numero_nf': self.numero_nf,
                'tipo': self.tipo,
                'valor_total': self.valor_total,
                'dados_adicionais': self.dados_adicionais,
            })
            print(f'processar_nf: {self.id} finalizado')
        except Exception as e:
            logger.error(f"Erro ao processar nota fiscal: {str(e)}")
            self.logs['erro'].append(str(e))
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
        infCTeNorm = infCte.find('.//cte:infCTeNorm', ns) or infCte.find('.//infCTeNorm', ns)
        chave_nf = ''
        if infCTeNorm is not None:
            infDoc = infCTeNorm.find('.//cte:infDoc', ns) or infCTeNorm.find('.//infDoc', ns)
            if infDoc is not None:
                infNFe = infDoc.find('.//cte:infNFe', ns) or infDoc.find('.//infNFe', ns)
                if infNFe is not None:
                    chave_nf = infNFe.findtext('.//cte:chave', default='', namespaces=ns)
                    
        
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
            'motorista': motorista,
            'chave_nf': chave_nf,
            'impostos': impostos
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
                #print(f'cobr: {cobr}')
                fatura = cobr.find('.//nfe:fat', ns) or cobr.find('.//fat', ns)
                #print(f'fatura: {fatura}')
                dup = cobr.find('.//nfe:dup', ns) or cobr.find('.//dup', ns)
                #print(f'dup: {dup}')
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
            
            dados_adicionais = {
                'fatura': {
                    'vencimento': None,
                    'numero_fatura': None,
                    'valor_total': None
                },
                'impostos': impostos
            }
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
                'dados_adicionais': dados_adicionais,
            }
            
            if cobr and dup:
                vencimento = get_xml_text(dup, './/nfe:dVenc', ns) or get_xml_text(dup, './/dVenc', ns)
                if vencimento:
                    vencimento = datetime.strptime(vencimento, '%Y-%m-%d')
                    # Converter para string para serialização JSON
                    vencimento_str = vencimento.strftime('%Y-%m-%d')
                else:
                    vencimento = None
                    vencimento_str = None
                #print(f'vencimento: {vencimento}')
                if fatura:
                    #print(f'fatura: {fatura}')
                    numero_fatura = get_xml_text(fatura, './/nfe:nFat', ns) or get_xml_text(fatura, './/nFat', ns)
                    valor_total = get_xml_text(fatura, './/nfe:vOrig', ns) or get_xml_text(fatura, './/vOrig', ns)
                    valor_total = Decimal(valor_total)
                    nfe_data['dados_adicionais']['fatura'] = {
                        'vencimento': vencimento_str,  # Salvar como string para serialização JSON
                        'numero_fatura': numero_fatura,
                        'valor_total': str(valor_total)  # Converter Decimal para string também
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
                    xPed = get_xml_text(prod, './/nfe:xPed', ns) or get_xml_text(prod, './/xPed', ns) or ''
                    nItemPed = get_xml_text(prod, './/nfe:nItemPed', ns) or get_xml_text(prod, './/nItemPed', ns) or ''
                    impostos = item.find('.//nfe:imposto', ns) or item.find('.//imposto', ns)
                    ICMS = impostos.find('.//nfe:ICMS', ns) or impostos.find('.//ICMS', ns)
                    if ICMS:   
                        ICMS60 = ICMS.find('.//nfe:ICMS60', ns) or ICMS.find('.//ICMS60', ns)
                    else:
                        ICMS60 = None
                    IPI = impostos.find('.//nfe:IPI', ns) or impostos.find('.//IPI', ns)
                    if IPI: 
                        IPITrib = IPI.find('.//nfe:IPITrib', ns) or IPI.find('.//IPITrib', ns)
                    else:
                        IPITrib = None
                    PIS = impostos.find('.//nfe:PIS', ns) or impostos.find('.//PIS', ns)
                    if PIS:
                        PISAliq = PIS.find('.//nfe:PISAliq', ns) or PIS.find('.//PISAliq', ns)
                    else:
                        PISAliq = None
                    COFINS = impostos.find('.//nfe:COFINS', ns) or impostos.find('.//COFINS', ns)
                    if COFINS:
                        COFINSAliq = COFINS.find('.//nfe:COFINSAliq', ns) or COFINS.find('.//COFINSAliq', ns)
                    else:
                        COFINSAliq = None
                    
                    impostos = {
                        'ICMS': {
                            'CST': ICMS60.findtext('.//nfe:CST', default='0', namespaces=ns) or ICMS60.findtext('.//CST', default='0', namespaces=ns) if ICMS60 else None,
                            'vBCSTRet': ICMS60.findtext('.//nfe:vBCSTRet', default='0', namespaces=ns) or ICMS60.findtext('.//vBCSTRet', default='0', namespaces=ns) if ICMS60 else None,
                            'pST': ICMS60.findtext('.//nfe:pST', default='0', namespaces=ns) or ICMS60.findtext('.//pST', default='0', namespaces=ns) if ICMS60 else None,
                            'vICMSSTRet': ICMS60.findtext('.//nfe:vICMSSTRet', default='0', namespaces=ns) or ICMS60.findtext('.//vICMSSTRet', default='0', namespaces=ns) if ICMS60 else None,
                            'vICMSSubstituto': ICMS60.findtext('.//nfe:vICMSSubstituto', default='0', namespaces=ns) or ICMS60.findtext('.//vICMSSubstituto', default='0', namespaces=ns) if ICMS60 else None,
                        },
                        'IPI': {
                            'CST': IPITrib.findtext('.//nfe:CST', default='0', namespaces=ns) or IPITrib.findtext('.//CST', default='0', namespaces=ns) if IPITrib else None,
                            'vBC': IPITrib.findtext('.//nfe:vBC', default='0', namespaces=ns) or IPITrib.findtext('.//vBC', default='0', namespaces=ns) if IPITrib else None,
                            'pIPI': IPITrib.findtext('.//nfe:pIPI', default='0', namespaces=ns) or IPITrib.findtext('.//pIPI', default='0', namespaces=ns) if IPITrib else None,
                            'vIPI': IPITrib.findtext('.//nfe:vIPI', default='0', namespaces=ns) or IPITrib.findtext('.//vIPI', default='0', namespaces=ns) if IPITrib else None,
                        },
                        'PIS': {
                            'CST': PISAliq.findtext('.//nfe:CST', default='0', namespaces=ns) or PISAliq.findtext('.//CST', default='0', namespaces=ns) if PISAliq else None,
                            'vBC': PISAliq.findtext('.//nfe:vBC', default='0', namespaces=ns) or PISAliq.findtext('.//vBC', default='0', namespaces=ns) if PISAliq else None,
                            'pPIS': PISAliq.findtext('.//nfe:pPIS', default='0', namespaces=ns) or PISAliq.findtext('.//pPIS', default='0', namespaces=ns) if PISAliq else None,
                            'vPIS': PISAliq.findtext('.//nfe:vPIS', default='0', namespaces=ns) or PISAliq.findtext('.//vPIS', default='0', namespaces=ns) if PISAliq else None,
                        },
                        'COFINS': {
                            'CST': COFINSAliq.findtext('.//nfe:CST', default='0', namespaces=ns) or COFINSAliq.findtext('.//CST', default='0', namespaces=ns) if COFINSAliq else None,
                            'vBC': COFINSAliq.findtext('.//nfe:vBC', default='0', namespaces=ns) or COFINSAliq.findtext('.//vBC', default='0', namespaces=ns) if COFINSAliq else None,
                            'pCOFINS': COFINSAliq.findtext('.//nfe:pCOFINS', default='0', namespaces=ns) or COFINSAliq.findtext('.//pCOFINS', default='0', namespaces=ns) if COFINSAliq else None,
                            'vCOFINS': COFINSAliq.findtext('.//nfe:vCOFINS', default='0', namespaces=ns) or COFINSAliq.findtext('.//vCOFINS', default='0', namespaces=ns) if COFINSAliq else None,
                        },
                    }
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
                            'xPed': xPed,
                            'nItemPed': nItemPed,
                            'infAdProd': infAdProd,
                            'impostos': impostos
                            }
                        }
                    
                    nfe_data['itens'].append(item_data)
                except Exception as e:
                    logger.error(f"Erro ao processar item {num_item}: {str(e)}")
            
            return chave_acesso, nfe_data
        
        except Exception as e:
            logger.error(f"Erro ao extrair dados do XML: {str(e)}")
            return None, None
    def _nfse_dict_get(self, obj, *path):
        """Obtém valor aninhado em dict do xmltodict, suportando chaves com namespace e listas de 1 elemento."""
        for key in path:
            if obj is None or not isinstance(obj, dict):
                return None
            val = obj.get(key)
            if val is None and isinstance(obj, dict):
                for k, v in obj.items():
                    if k == key or (k.startswith('{') and k.endswith('}' + key)):
                        val = v
                        break
            if val is not None and isinstance(val, list) and len(val) == 1:
                val = val[0]
            obj = val
        return obj

    def _nfse_text(self, val):
        """Extrai texto de valor do xmltodict (string, dict com #text ou atributo @id)."""
        if val is None:
            return ''
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, dict):
            return (val.get('#text') or val.get('@Id') or '').strip() if isinstance(val.get('#text') or val.get('@Id'), str) else ''
        return str(val).strip() if val else ''

    def _nfse_val(self, d, key):
        """Obtém valor de d por key ou por chave com namespace (ex.: {uri}key)."""
        if not d or not isinstance(d, dict):
            return None
        if d.get(key) is not None:
            return d.get(key)
        for k, v in d.items():
            if isinstance(k, str) and (k == key or k.endswith('}' + key)):
                return v
        return None

    def _extrair_nfse_lista_nfse(self, root):
        """Formato ListaNfse > CompNfse > Nfse > InfNfse (ex.: XML 40 - VALE)."""
        comp = self._nfse_dict_get(root, 'ListaNfse', 'CompNfse')
        nfse_el = self._nfse_dict_get(comp, 'Nfse') if comp else None
        inf = self._nfse_dict_get(nfse_el, 'InfNfse') if nfse_el else None
        if not inf:
            return None, None
        if isinstance(inf, list):
            inf = inf[0] if inf else None
        if not inf or not isinstance(inf, dict):
            return None, None
        chave = (inf.get('@Id') or '').strip()
        if chave.startswith('NFS'):
            chave = chave[3:]
        decl = self._nfse_dict_get(inf, 'DeclaracaoPrestacaoServico', 'InfDeclaracaoPrestacaoServico')
        if isinstance(decl, list):
            decl = decl[0] if decl else None
        dados_adicionais = {
            'id': chave,
            'cancelada': self._nfse_text(inf.get('Status')) == '2',
            'Rps': {'Numero': None, 'Serie': None, 'DataEmissao': None, 'DataVencimento': None},
            'Servico': {'Valores': {'Aliquota': None, 'ValorConfins': None, 'ValorIss': None, 'ValorPis': None, 'ValorServicos': None}, 'IssRetido': None, 'Discriminacao': None},
        }
        valores_nfse = self._nfse_dict_get(inf, 'ValoresNfse')
        valores = None
        if valores_nfse and isinstance(valores_nfse, dict):
            valores = {
                'BaseCalculo': self._nfse_text(valores_nfse.get('BaseCalculo')),
                'Aliquota': self._nfse_text(valores_nfse.get('Aliquota')),
                'ValorIss': self._nfse_text(valores_nfse.get('ValorIss')),
                'ValorLiquidoNfse': self._nfse_text(valores_nfse.get('ValorLiquidoNfse')),
            }
        prestador = self._nfse_dict_get(inf, 'PrestadorServico')
        cnpj_emitente = None
        nome_emitente = self._nfse_text(prestador.get('RazaoSocial')) if prestador else ''
        if decl:
            prest = self._nfse_dict_get(decl, 'Prestador')
            if prest:
                cpf_cnpj = self._nfse_dict_get(prest, 'CpfCnpj')
                if cpf_cnpj:
                    cnpj_emitente = self._nfse_text(cpf_cnpj.get('Cnpj')) or self._nfse_text(cpf_cnpj.get('Cpf'))
            if not nome_emitente and prestador:
                nome_emitente = self._nfse_text(prestador.get('RazaoSocial'))
        tomador_el = self._nfse_dict_get(decl, 'TomadorServico') if decl else None
        cnpj_dest = None
        nome_dest = ''
        if tomador_el:
            id_tom = self._nfse_dict_get(tomador_el, 'IdentificacaoTomador', 'CpfCnpj')
            if id_tom and isinstance(id_tom, dict):
                cnpj_dest = self._nfse_text(id_tom.get('Cnpj')) or self._nfse_text(id_tom.get('Cpf'))
            nome_dest = self._nfse_text(tomador_el.get('RazaoSocial'))
        if decl:
            serv = self._nfse_dict_get(decl, 'Servico')
            if serv:
                vals = self._nfse_dict_get(serv, 'Valores')
                if vals and isinstance(vals, dict):
                    dados_adicionais['Servico']['Valores']['Aliquota'] = self._nfse_text(vals.get('Aliquota'))
                    dados_adicionais['Servico']['Valores']['ValorConfins'] = self._nfse_text(vals.get('ValorCofins'))
                    dados_adicionais['Servico']['Valores']['ValorIss'] = self._nfse_text(vals.get('ValorIss'))
                    dados_adicionais['Servico']['Valores']['ValorPis'] = self._nfse_text(vals.get('ValorPis'))
                    dados_adicionais['Servico']['Valores']['ValorServicos'] = self._nfse_text(vals.get('ValorServicos'))
                dados_adicionais['Servico']['IssRetido'] = self._nfse_text(serv.get('IssRetido'))
                dados_adicionais['Servico']['Discriminacao'] = self._nfse_text(serv.get('Discriminacao'))
            inf_comp = self._nfse_dict_get(decl, 'InformacoesComplementares')
            if inf_comp:
                dados_adicionais['InformacoesComplementares'] = self._nfse_text(inf_comp) if isinstance(inf_comp, str) else (inf_comp.get('#text') or '')
        dados_nfse = {
            'Numero': self._nfse_text(inf.get('Numero')),
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente or self._nfse_text(prestador.get('RazaoSocial')) if prestador else '',
            'cnpj_destinatario': cnpj_dest,
            'nome_destinatario': nome_dest,
            'DataEmissao': self._nfse_text(inf.get('DataEmissao')),
            'valores': valores,
            'dados_adicionais': dados_adicionais,
        }
        return chave, dados_nfse

    def _extrair_nfse_tc_lista(self, root):
        """Formato tcListaNFse (EL) com namespace - ex.: NF 35 - VALE."""
        for key in list(root.keys()):
            if key == 'tcListaNFse' or (isinstance(key, str) and key.endswith('}tcListaNFse')):
                tc = root[key]
                break
        else:
            return None, None
        nfse_el = self._nfse_dict_get(tc, 'Nfse')
        if not nfse_el or not isinstance(nfse_el, dict):
            return None, None
        chave = self._nfse_text(self._nfse_val(nfse_el, 'Id'))
        ident = self._nfse_dict_get(nfse_el, 'IdentificacaoNfse')
        numero = self._nfse_text(self._nfse_val(ident, 'Numero')) if ident else self._nfse_text(self._nfse_val(nfse_el, 'Numero'))
        data_emissao = self._nfse_text(self._nfse_val(nfse_el, 'DataEmissao'))
        if data_emissao and 'T' in data_emissao:
            data_emissao = data_emissao[:10]
        dados_adicionais = {
            'id': chave,
            'cancelada': self._nfse_text(self._nfse_val(nfse_el, 'Status')) == '2',
            'Rps': {'Numero': self._nfse_text(self._nfse_val(ident, 'NumeroRps')) if ident else None, 'Serie': self._nfse_text(self._nfse_val(ident, 'Serie')) if ident else None, 'DataEmissao': None, 'DataVencimento': None},
            'Servico': {'Valores': {'Aliquota': None, 'ValorConfins': None, 'ValorIss': None, 'ValorPis': None, 'ValorServicos': None}, 'IssRetido': None, 'Discriminacao': None},
        }
        valores_el = self._nfse_dict_get(nfse_el, 'Valores')
        valores = None
        if valores_el and isinstance(valores_el, dict):
            valores = {
                'BaseCalculo': '',
                'Aliquota': self._nfse_text(self._nfse_val(valores_el, 'Aliquota')),
                'ValorIss': self._nfse_text(self._nfse_val(valores_el, 'ValorIss')),
                'ValorLiquidoNfse': self._nfse_text(self._nfse_val(valores_el, 'ValorLiquidoNfse')),
            }
        servicos_el = self._nfse_dict_get(nfse_el, 'Servicos')
        if servicos_el and isinstance(servicos_el, dict):
            dados_adicionais['Servico']['Valores']['Aliquota'] = self._nfse_text(self._nfse_val(servicos_el, 'Aliquota'))
            dados_adicionais['Servico']['Valores']['ValorServicos'] = self._nfse_text(self._nfse_val(servicos_el, 'ValorServico') or self._nfse_val(valores_el, 'ValorServicos') if valores_el else None)
            dados_adicionais['Servico']['Discriminacao'] = self._nfse_text(self._nfse_val(servicos_el, 'Descricao'))
        if valores_el and isinstance(valores_el, dict) and not dados_adicionais['Servico']['Valores']['ValorServicos']:
            dados_adicionais['Servico']['Valores']['ValorServicos'] = self._nfse_text(self._nfse_val(valores_el, 'ValorServicos'))
        dados_adicionais['Servico']['IssRetido'] = self._nfse_text(self._nfse_val(nfse_el, 'IssRetido'))
        obs = self._nfse_text(self._nfse_val(nfse_el, 'Observacao'))
        if obs:
            dados_adicionais['InformacoesComplementares'] = obs
        prest = self._nfse_dict_get(nfse_el, 'DadosPrestador', 'IdentificacaoPrestador')
        cnpj_emitente = self._nfse_text(self._nfse_val(prest, 'CpfCnpj')) if prest and isinstance(prest, dict) else ''
        if not cnpj_emitente:
            prest_root = self._nfse_dict_get(nfse_el, 'DadosPrestador')
            cnpj_emitente = self._nfse_text(self._nfse_val(prest_root, 'CpfCnpj')) if prest_root and isinstance(prest_root, dict) else ''
        dados_prest = self._nfse_dict_get(nfse_el, 'DadosPrestador')
        nome_emitente = self._nfse_text(self._nfse_val(dados_prest, 'RazaoSocial')) if dados_prest else ''
        tomador = self._nfse_dict_get(nfse_el, 'DadosTomador')
        id_tom = self._nfse_dict_get(tomador, 'IdentificacaoTomador') if tomador else None
        cnpj_dest = self._nfse_text(self._nfse_val(id_tom, 'CpfCnpj')) if id_tom and isinstance(id_tom, dict) else ''
        if not cnpj_dest and tomador:
            cnpj_dest = self._nfse_text(self._nfse_val(tomador, 'CpfCnpj'))
        nome_dest = self._nfse_text(self._nfse_val(tomador, 'RazaoSocial')) if tomador and isinstance(tomador, dict) else ''
        dados_nfse = {
            'Numero': numero,
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente,
            'cnpj_destinatario': cnpj_dest,
            'nome_destinatario': nome_dest,
            'DataEmissao': data_emissao,
            'valores': valores,
            'dados_adicionais': dados_adicionais,
        }
        return chave, dados_nfse

    def _extrair_nfse_sped(self, root):
        """Formato NFSe SPED (namespace sped.fazenda.gov.br/nfse) - ex.: 27126...8.xml."""
        for key in list(root.keys()):
            if key == 'NFSe' or (isinstance(key, str) and key.endswith('}NFSe')):
                nfse_root = root[key]
                break
        else:
            return None, None
        inf_nfse = self._nfse_dict_get(nfse_root, 'infNFSe')
        if not inf_nfse or not isinstance(inf_nfse, dict):
            return None, None
        chave = self._nfse_text(inf_nfse.get('@Id') or '')
        if chave.startswith('NFS'):
            chave = chave[3:]
        numero = self._nfse_text(self._nfse_val(inf_nfse, 'nNFSe'))
        data_emissao = ''
        emit = self._nfse_dict_get(inf_nfse, 'emit')
        cnpj_emitente = self._nfse_text(self._nfse_val(emit, 'CNPJ')) if emit and isinstance(emit, dict) else ''
        nome_emitente = self._nfse_text(self._nfse_val(emit, 'xNome')) if emit and isinstance(emit, dict) else ''
        valores_raiz = self._nfse_dict_get(inf_nfse, 'valores')
        v_liq = self._nfse_text(self._nfse_val(valores_raiz, 'vLiq')) if valores_raiz and isinstance(valores_raiz, dict) else ''
        dps = self._nfse_dict_get(inf_nfse, 'DPS', 'infDPS')
        if isinstance(dps, list):
            dps = dps[0] if dps else None
        if dps and isinstance(dps, dict):
            data_emissao = self._nfse_text(self._nfse_val(dps, 'dhEmi'))
            if data_emissao and 'T' in data_emissao:
                data_emissao = data_emissao[:10]
            toma = self._nfse_dict_get(dps, 'toma')
            cnpj_dest = self._nfse_text(self._nfse_val(toma, 'CNPJ')) if toma and isinstance(toma, dict) else ''
            nome_dest = self._nfse_text(self._nfse_val(toma, 'xNome')) if toma and isinstance(toma, dict) else ''
        else:
            cnpj_dest = ''
            nome_dest = ''
        v_serv = ''
        if dps and isinstance(dps, dict):
            v_serv_prest = self._nfse_dict_get(dps, 'valores', 'vServPrest')
            if v_serv_prest and isinstance(v_serv_prest, dict):
                v_serv = self._nfse_text(self._nfse_val(v_serv_prest, 'vServ'))
        valores = {
            'BaseCalculo': '',
            'Aliquota': '',
            'ValorIss': '',
            'ValorLiquidoNfse': v_liq or '',
        }
        dados_adicionais = {
            'id': chave,
            'cancelada': False,
            'Rps': {'Numero': None, 'Serie': None, 'DataEmissao': None, 'DataVencimento': None},
            'Servico': {'Valores': {'Aliquota': None, 'ValorConfins': None, 'ValorIss': None, 'ValorPis': None, 'ValorServicos': v_serv or None}, 'IssRetido': None, 'Discriminacao': None},
        }
        dados_nfse = {
            'Numero': numero,
            'cnpj_emitente': cnpj_emitente,
            'nome_emitente': nome_emitente,
            'cnpj_destinatario': cnpj_dest,
            'nome_destinatario': nome_dest,
            'DataEmissao': data_emissao,
            'valores': valores,
            'dados_adicionais': dados_adicionais,
        }
        return chave, dados_nfse

    def extrair_dados_xml_nfse(self):
        """
        Extrai os dados de uma nota fiscal de serviço (NFSe) a partir do XML.
        Suporta três formatos: ListaNfse (padrão ABRASF), tcListaNFse (EL) e NFSe SPED.
        Retorna a chave de acesso e um dicionário com os dados da nota fiscal.
        """
        try:
            root = self.get_xml_json()
            if not root or not isinstance(root, dict):
                logger.warning("extrair_dados_xml_nfse: XML inválido ou vazio")
                return None, None

            def _tem_chave(d, *keys):
                for k in keys:
                    if d.get(k) is not None:
                        return True
                    for key in d:
                        if isinstance(key, str) and (key == k or key.endswith('}' + k)):
                            return True
                return False

            if _tem_chave(root, 'ListaNfse'):
                chave, dados = self._extrair_nfse_lista_nfse(root)
            elif _tem_chave(root, 'tcListaNFse'):
                chave, dados = self._extrair_nfse_tc_lista(root)
            elif _tem_chave(root, 'NFSe'):
                chave, dados = self._extrair_nfse_sped(root)
            else:
                logger.warning("extrair_dados_xml_nfse: Formato de XML NFSe não reconhecido")
                return None, None

            if not chave or not dados:
                return None, None
            if not dados.get('valores') or not self._nfse_text(dados['valores'].get('ValorLiquidoNfse')):
                if dados.get('valores') is None:
                    dados['valores'] = {'BaseCalculo': '', 'Aliquota': '', 'ValorIss': '', 'ValorLiquidoNfse': '0'}
                elif not dados['valores'].get('ValorLiquidoNfse'):
                    dados['valores']['ValorLiquidoNfse'] = '0'
            return chave, dados
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Erro ao extrair dados do XML NFSe: {str(e)}")
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
                    print(f'item_anterior: {item_anterior.material.nome}')
                    if comparar_unidades(item_anterior.unidade, item.unidade):
                        item.fator_conversao_aplicado = item_anterior.fator_conversao_aplicado
                        item.material_id = item_anterior.material_id
                        item.save()
                        db.session.commit()
                        db.session.refresh(item)
                        itens_vinculados += 1
                else:
                    print(f'item {item.id} não vinculado a um material do sistema')
                    self.logs['erro'].append(f'item {item.id} não vinculado a um material do sistema')
        self.logs['itens_vinculados'] = itens_vinculados
        return itens_vinculados
    def importar_itens_para_estoque(self, usuario_id=None, centro_custo_id=None, observacao=None):
        estatisticas = {
            'total_processados': 0,
            'total_importados': 0,
            'total_nao_vinculados': 0,
            'total_ja_importados': 0,
            'itens_com_erro': []
        }
        
        for item in self.itens:
            estatisticas['total_processados'] += 1
            
            # Verificar se já foi importado
            if item.importado_estoque:
                estatisticas['total_ja_importados'] += 1
                continue
            
            # Verificar se tem material vinculado
            if not item.material_id:
                estatisticas['total_nao_vinculados'] += 1
                estatisticas['itens_com_erro'].append({
                    'item_id': item.id,
                    'descricao': item.descricao,
                    'erro': 'Item não vinculado a um material do sistema'
                })
                continue
            
            # Tentar importar
            sucesso, mensagem, estatisticas_item = item.importar_para_estoque_automatico(
                usuario_id=usuario_id, 
                centro_custo_id=centro_custo_id, 
                observacao=observacao
            )
            
            if sucesso:
                estatisticas['total_importados'] += 1
            else:
                estatisticas['itens_com_erro'].append({
                    'item_id': item.id,
                    'descricao': item.descricao,
                    'erro': mensagem
                })
        self.estatisticas = estatisticas   
    def importar_pendentes_com_material(self, usuario_id, centro_custo_id=None, observacao=None):
        """
        Importa e vincula itens pendentes que já têm material vinculado.
        Para cada item já vinculado:
        1. Vincula itens similares em outras notas
        2. Importa o item atual e todos os similares encontrados
        
        Args:
            usuario_id: ID do usuário realizando a operação
            centro_custo_id: ID do centro de custo (opcional)
            observacao: Observação para a importação (opcional)
        
        Returns:
            dict: Dicionário com estatísticas da operação
        """
        from models.material import Material
        
        # Inicializar estatísticas
        estatisticas = {
            'total_processados': 0,
            'total_importados': 0,
            'total_nao_vinculados': 0,
            'total_ja_importados': 0,
            'total_itens_vinculados': 0,
            'total_itens_ja_vinculados': 0,
            'itens_com_erro': []
        }
        itens_processados = set()
        grupos_processados = set()
        
        # ETAPA 1: Vincular similares em todas as notas
        todos_itens_para_importar = []
        
        # Processar cada item já vinculado na nota atual
        for item in self.itens:
            if item.material_id and item.id not in itens_processados:
                material = Material.query.get(item.material_id)
                if not material:
                    continue
                
                # Vincular similares em todas as notas
                itens_similares = item.vincular_similares_em_todas_notas(
                    itens_processados=itens_processados,
                    grupos_processados=grupos_processados,
                    estatisticas=estatisticas
                )
                
                # Adicionar à lista de itens para importar (sem duplicatas)
                for item_similar in itens_similares:
                    if item_similar.id not in [i.id for i in todos_itens_para_importar]:
                        todos_itens_para_importar.append(item_similar)
        
        # ETAPA 2: Importar todos os itens (originais + similares recém-vinculados)
        logger.info(f'Iniciando importação de {len(todos_itens_para_importar)} itens para o estoque')
        estatisticas['total_processados'] = len(todos_itens_para_importar)
        NotaFiscalItem.importar_lista_itens(
            itens_para_importar=todos_itens_para_importar,
            nota_fiscal=self,
            usuario_id=usuario_id,
            centro_custo_id=centro_custo_id,
            observacao=observacao,
            itens_processados=itens_processados,
            estatisticas=estatisticas
        )
        
        # Calcular total de não vinculados
        estatisticas['total_nao_vinculados'] = sum(
            1 for item in todos_itens_para_importar 
            if not item.material_id
        )
        
        return estatisticas
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
    __tablename__ = 'NotaFiscalItem'
    
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
    unidade_id = db.Column(db.Integer, db.ForeignKey('Unidades.id'), nullable=True)
    unidade_rel = db.relationship('Unidades', back_populates='nf_itens', lazy=True)
    unidade_original = db.Column(db.String(6), nullable=True)
    quantidade_original = db.Column(db.Numeric(15, 4), nullable=True)
    fator_conversao_aplicado = db.Column(db.Numeric(15, 4), nullable=True)
    
    # Vinculação com material do sistema
    material_id = db.Column(db.Integer, db.ForeignKey('Materiais.id'), nullable=True)
    material = db.relationship('Materiais', backref='itens_nota_fiscal')

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
    nf_id = db.Column(db.Integer, db.ForeignKey('NotaFiscal.id', ondelete='CASCADE'), nullable=False)
    # Datas de controle
    data_criacao = db.Column(db.DateTime, default=datetime.now)
    data_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    estatisticas = None
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estatisticas = {
            'processados': 0,
            'itens_processados': [],
            'vinculacao':{
                'total': 0,
                'ja_vinculados': 0,
                'nao_vinculados': 0,
                'vinculadosn':0,
                'vinculados': [],
                'errosn': 0,
                'erros': [],
            },
            'importacao':{
                'total': 0,
                'ja_importados': 0,
                'nao_importados': 0,
                'importados': [],
                'importadosn':0,
                'errosn': 0,
                'erros': [],
            }
        }
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
        try:
            self.fator_conversao_aplicado = fator_conversao_aplicado
            self.material_id = material
            self.save()
            return True, None
        except Exception as e:
            print(f'erro ao vincular: {e}')
            return False, e
    def vincular_todos(self):
        inicio = datetime.now()
        itens = NotaFiscalItem.query.filter(NotaFiscalItem.codigo==self.codigo,
                                            NotaFiscalItem.descricao==self.descricao,
                                            NotaFiscalItem.unidade==self.unidade,
                                            NotaFiscalItem.nota_fiscal.has(NotaFiscal.cnpj_emitente == self.nota_fiscal.cnpj_emitente),
                                            NotaFiscalItem.material_id==None).all()
        print(f'itens a ser vinculados: {len(itens)}')
        for item in itens:
            item.vincular(self.fator_conversao_aplicado,self.material_id)
            item.save()
        fim = datetime.now()
        print(f'tempo de execucao vincular_todos: {fim - inicio}')
    def vincular_e_importar_estoque_todos(self,usuario_id=None, centro_custo_id=None, observacao=None):

        inicio = datetime.now()    
        itens = NotaFiscalItem.query.\
            join(NotaFiscal, NotaFiscalItem.nf_id == NotaFiscal.id).filter(
                            NotaFiscal.status_processamento!='cancelada',
                            NotaFiscalItem.codigo.like(f'%{self.codigo}%'),
                            NotaFiscalItem.descricao.like(f'%{self.descricao}%'),
                            NotaFiscalItem.nota_fiscal.has(NotaFiscal.cnpj_emitente == self.nota_fiscal.cnpj_emitente),
                            NotaFiscalItem.unidade.like(f'%{self.unidade}%')).all()
        print(f'itens a ser processados: {len(itens)}')
       
        print(f'material_id: {self.material_id}')
        print(f'fator_conversao_aplicado: {self.fator_conversao_aplicado}')
        
        for item in itens:
            # Inicializa estatisticas se não estiver inicializado
            if item.estatisticas is None:
                item.estatisticas = {
                    'processados': 0,
                    'itens_processados': [],
                    'vinculacao':{
                        'total': 0,
                        'ja_vinculados': 0,
                        'nao_vinculados': 0,
                        'vinculadosn':0,
                        'vinculados': [],
                        'errosn': 0,
                        'erros': [],
                    },
                    'importacao':{
                        'total': 0,
                        'ja_importados': 0,
                        'nao_importados': 0,
                        'importados': [],
                        'importadosn':0,
                        'errosn': 0,
                        'erros': [],
                    }
                }
            
            if item.material_id:
                item.estatisticas['vinculacao']['ja_vinculados'] += 1
            else:
                item.estatisticas['vinculacao']['nao_vinculados'] += 1
                sucesso, erro = item.vincular(self.fator_conversao_aplicado, self.material_id)
                item.material_id = self.material_id
                item.fator_conversao_aplicado = self.fator_conversao_aplicado
                if sucesso:
                    item.estatisticas['vinculacao']['vinculados'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id))
                    item.estatisticas['vinculacao']['vinculadosn'] += 1
                else:
                    item.estatisticas['vinculacao']['errosn'] += 1
                    item.estatisticas['vinculacao']['erros'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id))
                item.save()
                db.session.commit()
                db.session.refresh(item)
            if item.importado_estoque:
                item.estatisticas['importacao']['ja_importados'] += 1
            else:
                item.estatisticas['importacao']['nao_importados'] += 1
                print(f'importar_para_estoque_automatico: {item.id}')
                try:
                    sucesso, mensagem, estatisticas_item = item.importar_para_estoque_automatico(usuario_id=usuario_id, centro_custo_id=centro_custo_id, observacao=observacao)
                except Exception as e:
                    print(f'erro ao importar item {item.id}: {e}')
                    import traceback
                    traceback.print_exc()
                    print(f"Erro ao importar item {item.id}: {str(e)}")
                    item.estatisticas['importacao']['errosn'] += 1
                    item.estatisticas['importacao']['erros'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id)+':'+str(e))
                if sucesso:
                    print(f'item {item.id} importado com sucesso')
                    item.estatisticas['importacao']['importados'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id))
                    item.estatisticas['importacao']['importadosn'] += 1
                else:
                    item.estatisticas['importacao']['errosn'] += 1

                    item.estatisticas['importacao']['erros'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id)+':'+str(mensagem))

        fim = datetime.now()
        print(f'tempo de execucao vincular_e_importar_estoque_todos: {fim - inicio}')
        
        # Consolida estatísticas de todos os itens processados
        estatisticas_finais = {
            'processados': len(itens),
            'itens_processados': [],
            'vinculacao':{
                'total': 0,
                'ja_vinculados': 0,
                'nao_vinculados': 0,
                'vinculadosn':0,
                'vinculados': [],
                'errosn': 0,
                'erros': [],
            },
            'importacao':{
                'total': 0,
                'ja_importados': 0,
                'nao_importados': 0,
                'importados': [],
                'importadosn':0,
                'errosn': 0,
                'erros': [],
            }
        }
        
        # Consolida estatísticas de cada item
        for item in itens:
            if item.estatisticas:
                # Consolida estatísticas de vinculação
                if 'vinculacao' in item.estatisticas:
                    estatisticas_finais['vinculacao']['ja_vinculados'] += item.estatisticas['vinculacao'].get('ja_vinculados', 0)
                    estatisticas_finais['vinculacao']['nao_vinculados'] += item.estatisticas['vinculacao'].get('nao_vinculados', 0)
                    estatisticas_finais['vinculacao']['vinculadosn'] += item.estatisticas['vinculacao'].get('vinculadosn', 0)
                    estatisticas_finais['vinculacao']['errosn'] += item.estatisticas['vinculacao'].get('errosn', 0)
                    estatisticas_finais['vinculacao']['vinculados'].extend(item.estatisticas['vinculacao'].get('vinculados', []))
                    estatisticas_finais['vinculacao']['erros'].extend(item.estatisticas['vinculacao'].get('erros', []))
                
                # Consolida estatísticas de importação
                if 'importacao' in item.estatisticas:
                    estatisticas_finais['importacao']['ja_importados'] += item.estatisticas['importacao'].get('ja_importados', 0)
                    estatisticas_finais['importacao']['nao_importados'] += item.estatisticas['importacao'].get('nao_importados', 0)
                    estatisticas_finais['importacao']['importadosn'] += item.estatisticas['importacao'].get('importadosn', 0)
                    estatisticas_finais['importacao']['errosn'] += item.estatisticas['importacao'].get('errosn', 0)
                    estatisticas_finais['importacao']['importados'].extend(item.estatisticas['importacao'].get('importados', []))
                    estatisticas_finais['importacao']['erros'].extend(item.estatisticas['importacao'].get('erros', []))
            
            estatisticas_finais['itens_processados'].append(f'nf:{item.nota_fiscal.id if item.nota_fiscal else "N/A"}:item:{item.id}')
        
        # Calcula totais
        estatisticas_finais['vinculacao']['total'] = estatisticas_finais['vinculacao']['ja_vinculados'] + estatisticas_finais['vinculacao']['nao_vinculados']
        estatisticas_finais['importacao']['total'] = estatisticas_finais['importacao']['ja_importados'] + estatisticas_finais['importacao']['nao_importados']
        
        # Determina sucesso e mensagem
        total_erros = estatisticas_finais['vinculacao']['errosn'] + estatisticas_finais['importacao']['errosn']
        sucesso = total_erros == 0 and len(itens) > 0
        
        mensagem = f"Processados {estatisticas_finais['processados']} itens. "
        mensagem += f"Vinculados: {estatisticas_finais['vinculacao']['vinculadosn']}, "
        mensagem += f"Importados: {estatisticas_finais['importacao']['importadosn']}"
        if total_erros > 0:
            mensagem += f". Erros: {total_erros}"
        
        return sucesso, mensagem, estatisticas_finais
    def importar_para_estoque_automatico(self, usuario_id=None, centro_custo_id=None, observacao=None):
        """
        Importa o item para o estoque processando todas as movimentações necessárias
        baseado na nota fiscal (pode ser múltiplas movimentações para transferências).
        
        Args:
            usuario_id: ID do usuário que está realizando a importação
            centro_custo_id: ID do centro de custo (opcional)
            observacao: Observação adicional para a movimentação
            
        Returns:
            tuple: (bool, str, dict) - (Sucesso, Mensagem, Estatísticas)
        """
        estatisticas = {
            'nota_fiscal_id': self.nota_fiscal.id,
            'item_id': self.id,
            'processado': True,
            'importado': False,
            'nao_vinculado': False,
            'ja_importado': False,
            'erro': None,
            'movimentacoes': []
        }
        
        # Verificar se já foi importado
        if self.importado_estoque:
            estatisticas['ja_importado'] = True
            return (False, "Item já foi importado para o estoque.", estatisticas)
        
        # Verificar se tem material vinculado
        if not self.material_id:
            estatisticas['nao_vinculado'] = True
            estatisticas['erro'] = 'Item não vinculado a um material do sistema'
            return (False, "Este item não está vinculado a um material do sistema.", estatisticas)
        
        # Determinar todas as movimentações necessárias
        movimentacoes = determinar_movimentacoes_estoque(self.nota_fiscal)
        
        estatisticas['movimentacoes'] = movimentacoes
        if not movimentacoes:
            print(f'Não há movimentações determinadas')
            estatisticas['erro'] = 'Não há movimentações determinadas'
            sucesso = False
            mensagem = 'Não há movimentações determinadas'
            return (sucesso, mensagem, estatisticas)
        
        # Processar todas as movimentações
        resultados = []
        for local, tipo_movimento in movimentacoes:
            sucesso, mensagem, stats = self.importar_para_estoque(
                usuario_id=usuario_id,
                centro_custo_id=centro_custo_id,
                observacao=observacao,
                local=local,
                tipo_movimento=tipo_movimento
            )
            resultados.append((sucesso, mensagem, stats))
            estatisticas.update(stats)
        
        print(f'resultados: {resultados}')
        # Verificar se houve erro em alguma movimentação
        for sucesso, mensagem, stats in resultados:
            if not sucesso:
                estatisticas['erro'] = mensagem
                return (False, mensagem, estatisticas)
        
        estatisticas['importado'] = True
        resultado_final = resultados[-1] if resultados else (True, "Item importado com sucesso", estatisticas)
        return (resultado_final[0], resultado_final[1], estatisticas)  
    def importar_para_estoque(self, usuario_id=None, centro_custo_id=None, observacao=None, local=None, tipo_movimento=None):
        """
        Importa o item da nota fiscal para o estoque
        
        Args:
            usuario_id: ID do usuário que está realizando a importação
            centro_custo_id: ID do centro de custo (opcional)
            observacao: Observação adicional para a movimentação
            local: Localização do estoque (opcional, será determinado automaticamente se não informado)
            tipo_movimento: Tipo de movimento 'entrada' ou 'saida' (opcional, será determinado automaticamente se não informado)
            
        Returns:
            tuple: (bool, str, dict) - (Sucesso, Mensagem, Estatísticas)
        """
        inicio = datetime.now()        
        estatisticas = {
            'processado': True,
            'importado': False,
            'nao_vinculado': False,
            'ja_importado': False,
            'erro': None
        }
        
        # Verificar se o item tem um material vinculado
        if not self.material_id:
            estatisticas['nao_vinculado'] = True
            estatisticas['erro'] = 'Item não vinculado a um material do sistema'
            return (False, "Este item não está vinculado a um material do sistema.", estatisticas)
        
        # Se local e tipo_movimento não foram informados, determinar automaticamente
        # Neste caso, verificar se já foi importado para evitar duplicação
        if local is None or tipo_movimento is None:
            return (False, "Local e tipo de movimento não foram informados.", estatisticas)
        
        try:
            # Buscar estoque existente para o material
            estoque = Estoque.query.filter_by(material_id=self.material_id,localizacao=local).first()
            
            # Se não existe estoque para este material, criar um novo
            if not estoque:
                print(f"Criando novo estoque para o material {self.material_id}")

                estoque = Estoque(
                    material_id=self.material_id,
                    tipo_item='material',
                    quantidade=float(self.quantidade),
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
            quantidade = 0
            # Adicionar informação sobre conversão de unidade, se aplicável
            fator = self.fator_conversao_aplicado if self.fator_conversao_aplicado is not None else 1
            if fator != 1:
                quantidade = self.quantidade * fator
                observacao += f" (Conversão: {float(self.quantidade):.2f} {self.unidade} → {float(quantidade):.2f} {estoque.material.unidade_obj.nome})"
            
            # Registrar a quantidade atual antes da atualização para log
            quantidade_anterior = float(estoque.quantidade) if estoque.quantidade else 0
            
            # Determinar usuario_id: priorizar o passado como parâmetro, depois current_user, depois None
            usuario_id_final = usuario_id
            if not usuario_id_final:
                try:
                    from flask_login import current_user
                    if current_user and hasattr(current_user, 'id'):
                        usuario_id_final = current_user.id
                except:
                    pass
            
            movimentacao = EstoqueMovimentacoes(
                estoque_id=estoque.id,
                tipo_movimento=tipo_movimento,
                quantidade=self.quantidade * fator,
                data_movimento=self.nota_fiscal.data_emissao,
                nota_fiscal_item_id=self.id,
                origem_tipo='NotaFiscal',
                origem_id=self.nota_fiscal.id,
                observacao=observacao,
                usuario_id=usuario_id_final
            )
            
            # Salvar movimentação (isso vai atualizar o estoque automaticamente)
            movimentacao.save()
            db.session.flush()
            
            
            # Garantir que o estoque seja atualizado corretamente
            
            
            # Verificar se a quantidade foi realmente atualizada
            quantidade_nova = float(estoque.quantidade) if estoque.quantidade else 0
            
            # Se a quantidade não foi atualizada, forçar a atualização diretamente
            if quantidade_nova <= quantidade_anterior:
                estoque.quantidade = quantidade_anterior + float(self.quantidade)
                estoque.save()
                quantidade_nova = float(estoque.quantidade)
            
        
            # Para importação automática (sem local/tipo especificado), marcar como importado
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
            if self.material and self.material.categoria == 'EPI':
                # Verificar se já existe um EPI para este material
                epi_existente = Epi.query.filter_by(material_id=self.material_id).first()
                
                if not epi_existente:
                    # Criar um novo registro de EPI
                    epi = Epi()
                    epi.material_id = self.material_id
                    epi.estoque_minimo = 1  # Valor padrão
                    epi.usuario_id = usuario_id
                    
                    # Salvar o EPI (não precisa adicionar estoque, pois já foi criado como material)
                    epi.save()
                    
                    # Adicionar mensagem sobre a criação do EPI
                    mensagem_extra = f" Material identificado como EPI. Registro de EPI criado automaticamente."
                    estatisticas['importado'] = True
                    return (True, f"Item importado com sucesso. {self.quantidade} {self.unidade or ''} adicionado(s) ao estoque. Estoque anterior: {quantidade_anterior}, Estoque atual: {quantidade_nova}{mensagem_extra}", estatisticas)
            
            estatisticas['importado'] = True
            return (True, f"Item importado com sucesso. {self.quantidade} {self.unidade or ''} adicionado(s) ao estoque. Estoque anterior: {quantidade_anterior}, Estoque atual: {quantidade_nova}", estatisticas)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # Registrar a tentativa
            self.ultima_tentativa_importacao = datetime.now()
            self.tentativas_importacao += 1
            self.status_importacao = 'Erro'
            self.dados_adicionais = str(e)
            self.save()
            
            estatisticas['erro'] = str(e)
            return (False, f"Erro ao importar item para estoque: {str(e)}", estatisticas)
    
    @staticmethod
    def buscar_itens_similares_todas_notas(codigo, descricao):
        """
        Busca todos os itens similares em todas as notas fiscais baseado em código e/ou descrição.
        
        Args:
            codigo: Código do item
            descricao: Descrição do item
        
        Returns:
            Lista de NotaFiscalItem encontrados
        """
        if codigo and descricao:
            return NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo,
                NotaFiscalItem.descricao == descricao
            ).all()
        elif codigo:
            return NotaFiscalItem.query.filter(
                NotaFiscalItem.codigo == codigo
            ).all()
        elif descricao:
            return NotaFiscalItem.query.filter(
                NotaFiscalItem.descricao == descricao
            ).all()
        return []
    def aplicar_fator_conversao(self, material, fator_conversao=None):
        """
        Aplica o fator de conversão ao item baseado no material e fator fornecido.
        
        Args:
            material: Material
            fator_conversao: Fator de conversão a ser aplicado (opcional)
        """
        if fator_conversao:
            try:
                self.fator_conversao_aplicado = float(fator_conversao)
            except (ValueError, TypeError):
                if comparar_unidades(self.unidade, material.unidade_obj.nome):
                    self.fator_conversao_aplicado = 1
                else:
                    self.fator_conversao_aplicado = None
        elif comparar_unidades(self.unidade, material.unidade_obj.nome):
            self.fator_conversao_aplicado = 1
        else:
            self.fator_conversao_aplicado = None
    def vincular_material_a_itens_similares(self, itens_sem_material, itens_processados):
        """
        Vincula o material aos itens similares que não têm material vinculado.
        
        Args:
            itens_sem_material: Lista de itens similares sem material
            itens_processados: Set de IDs de itens já processados
        
        Returns:
            Número de itens vinculados
        """
        if not self.material_id:
            return 0
            
        from models.material import Material
        material = Material.query.get(self.material_id)
        if not material:
            return 0
            
        itens_vinculados = 0
        fator_conversao = self.fator_conversao_aplicado
        
        for item_similar in itens_sem_material:
            if item_similar.id in itens_processados:
                continue
            
            item_similar.aplicar_fator_conversao(material, fator_conversao)
            item_similar.material_id = self.material_id
            item_similar.save()
            
            itens_vinculados += 1
            itens_processados.add(item_similar.id)
            logger.info(f'Item {item_similar.id} vinculado ao material {material.nome} na nota {item_similar.nota_fiscal.numero_nf}')
        
        return itens_vinculados
    def vincular_similares_em_todas_notas(self, itens_processados, grupos_processados, estatisticas):
        """
        Vincula itens similares em todas as notas para este item.
        
        Args:
            itens_processados: Set de IDs de itens já processados
            grupos_processados: Set de chaves de grupos já processados
            estatisticas: Dicionário com estatísticas da operação
        
        Returns:
            Lista de todos os itens similares encontrados (incluindo o original)
        """
        if not self.material_id:
            return []
            
        from models.material import Material
        material = Material.query.get(self.material_id)
        if not material:
            return []
            
        codigo = self.codigo.strip() if self.codigo else ''
        descricao = self.descricao.strip() if self.descricao else ''
        
        # Criar chave única para o grupo de itens similares
        chave_grupo = f"{codigo}|{descricao}"
        if chave_grupo in grupos_processados:
            return []  # Já processamos este grupo
        
        grupos_processados.add(chave_grupo)
        
        # 1. Buscar TODOS os itens similares em TODAS as notas fiscais
        logger.info(f'Buscando itens similares para código="{codigo}", descrição="{descricao}" em TODAS as notas fiscais')
        itens_similares_todos = NotaFiscalItem.buscar_itens_similares_todas_notas(codigo, descricao)
        logger.info(f'Encontrados {len(itens_similares_todos)} itens similares em todas as notas')
        
        # Separar itens já vinculados dos que não têm material
        itens_ja_vinculados_local = [i for i in itens_similares_todos if i.material_id]
        itens_sem_material = [i for i in itens_similares_todos if not i.material_id]
        logger.info(f'Dos {len(itens_similares_todos)} itens similares: {len(itens_ja_vinculados_local)} já vinculados, {len(itens_sem_material)} sem material')
        
        # 2. Vincular material aos itens que não têm material vinculado
        itens_vinculados_local = self.vincular_material_a_itens_similares(
            itens_sem_material, itens_processados
        )
        estatisticas['total_itens_vinculados'] += itens_vinculados_local
        estatisticas['total_itens_ja_vinculados'] += len(itens_ja_vinculados_local)
        
        # Retornar todos os itens similares (incluindo o original)
        return [self] + itens_similares_todos
    @staticmethod
    def importar_lista_itens(itens_para_importar, nota_fiscal, usuario_id, centro_custo_id, observacao, 
                             itens_processados, estatisticas):
        """
        Importa uma lista de itens para o estoque.
        
        Args:
            itens_para_importar: Lista de itens para importar
            nota_fiscal: Nota fiscal relacionada
            usuario_id: ID do usuário
            centro_custo_id: ID do centro de custo
            observacao: Observação para importação
            itens_processados: Set de IDs de itens já processados
            estatisticas: Dicionário com estatísticas da operação
        """
        # Garantir que todas as chaves necessárias existam
        if 'total_importados' not in estatisticas:
            estatisticas['total_importados'] = 0
        if 'total_ja_importados' not in estatisticas:
            estatisticas['total_ja_importados'] = 0
        if 'total_nao_vinculados' not in estatisticas:
            estatisticas['total_nao_vinculados'] = 0
        if 'total_itens_importados' not in estatisticas:
            estatisticas['total_itens_importados'] = 0
        if 'total_itens_ja_importados' not in estatisticas:
            estatisticas['total_itens_ja_importados'] = 0
        if 'itens_com_erro' not in estatisticas:
            estatisticas['itens_com_erro'] = []
        
        for item_para_importar in itens_para_importar:
            if item_para_importar.id in itens_processados:
                if item_para_importar.importado_estoque:
                    estatisticas['total_itens_ja_importados'] += 1
                continue
            
            if item_para_importar.material_id:
                if not item_para_importar.importado_estoque:
                    sucesso, mensagem, stats = item_para_importar.importar_para_estoque_automatico(
                        usuario_id=usuario_id,
                        centro_custo_id=centro_custo_id,
                        observacao=observacao or f"Importação automática da NF {nota_fiscal.numero_nf} de {nota_fiscal.nome_emitente}"
                    )
                    if sucesso:
                        estatisticas['total_itens_importados'] += 1
                        estatisticas['total_importados'] += 1
                        logger.info(f'Item {item_para_importar.id} importado para o estoque')
                    else:
                        estatisticas['itens_com_erro'].append({
                            'item_id': item_para_importar.id,
                            'descricao': item_para_importar.descricao,
                            'erro': mensagem
                        })
                        logger.error(f'Erro ao importar item {item_para_importar.id}: {mensagem}')
                else:
                    estatisticas['total_itens_ja_importados'] += 1
                    estatisticas['total_ja_importados'] += 1
            else:
                estatisticas['total_nao_vinculados'] += 1
            
            itens_processados.add(item_para_importar.id)
    def __repr__(self):
        """
        Representação em string do item de nota fiscal
        """
        return f'<NotaFiscalItem {self.id} - {self.descricao[:30]}>' 