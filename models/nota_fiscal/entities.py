from models.database import db
from datetime import datetime
from sqlalchemy.orm import defer
from sqlalchemy import SmallInteger, func

import json
from flask_login import current_user
import base64
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

from utils.utils import parse_dados_json
from .constants import (
    CNPJS_FILIAIS,
    CNPJS_MATRIZ,
    CNPJS_MATRIZ_FILIAIS,
    CFOPS_COMPRA,
    CFOPS_VENDA,
    CFOPS_TRANSFERENCIA,
)
from .movimentacao_estoque import determinar_movimentacoes_estoque

logger = logging.getLogger(__name__)
from models.nota_fiscal.constants import ARQUIVEI_API_ID, ARQUIVEI_API_KEY

# Nota Fiscal
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
    chave_nf = db.Column(db.String(44), nullable=True)
    # Relacionamentos
    itens = db.relationship('NotaFiscalItem', backref='nota_fiscal', cascade='all, delete-orphan')

    upload = None
    cancelada = False
    pdf = None
    inserido = False
    existente = False
    logs = None
    data = None

    
    def __init__(self, data=None, xml_data=None,chave_acesso=None, id=None, cancelada=False,tipo=None,pdf_data=None):
       
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
        self.xml_data = xml_data
        if data and not xml_data:
           
            self.xml_data = data.get('xml',None) 

            self.chave_acesso = data.get('chave_acesso',None)
        nota = None
        # Durante o __init__ essa instância pode estar "meio preenchida" e/ou já ter sido
        # adicionada ao session por algum processar_*; qualquer query aqui dispara autoflush.
        # Para evitar FlushError (tentativa de UPDATE com PK NULL), fazemos a busca sem autoflush.
        if self.chave_acesso:
            with db.session.no_autoflush:
                nota = NotaFiscal.query.filter(NotaFiscal.chave_acesso == self.chave_acesso).first()
            if nota:
                for key, value in nota.__dict__.items():
                    # nunca copiar estado interno do SQLAlchemy (ex: _sa_instance_state)
                    if key.startswith('_'):
                        continue
                    setattr(self, key, value)
            
        if not tipo and not nota:
            self.extrair_tipo_nota()

        if self.tipo and not nota:
            if self.tipo == 'nfe':
                self.processar_nfe()
            elif self.tipo == 'cte':
                self.processar_cte()
            elif self.tipo == 'nfse':
                self.processar_nfse()
             
        # Se a chave veio via `data`, o parâmetro `chave_acesso` pode estar None.
        # Neste caso, usamos `self.chave_acesso` para recarregar do banco e obter o `id`.
        
                
        if id:
            nota = NotaFiscal.query.get_or_404(id)
            if nota:
                for key, value in nota.__dict__.items():
                    if key.startswith('_'):
                        continue
                    setattr(self, key, value)
                    
                upload = Upload.query.filter_by(pai='NotaFiscal', pai_id=self.id, tipo=1).first()
                if not upload:
                    pdf_data = Arquivei(chave_acesso=self.chave_acesso)
                    #print(f'pdf_data: {pdf_data}')
                    logger.debug("id: %s chave: %s", self.id, self.chave_acesso)
                    self.upload = Upload.registrar(
                        pai='NotaFiscal',
                        pai_id=self.id,
                        tipo=1,
                        filename=f'{self.chave_acesso}.pdf',
                        mimetype='application/pdf',
                        blob=pdf_data.pdf,
                        dados_adicionais=self.dados_adicionais
                    )
                else:
                    if 'storage' not in upload.dados_adicionais:
                        pdf_data = Arquivei(chave_acesso=self.chave_acesso, pdf=True)
                        upload.blob = pdf_data.pdf
                        upload.save()
                    self.upload = upload
                #print('self.upload: ',self.upload)
    def extrair_tipo_nota(self):
        """
        Extrai o tipo de nota fiscal do XML
        """

        dicta = self.get_xml_json()
        
        #print(f'dicta: {dicta}')
        if dicta.get('CompNfse',None) or dicta.get('tcListaNFse',None) or dicta.get('ListaNfse',None) or dicta.get('NFSe',None):
            self.tipo = 'nfse'
        elif dicta.get('nfeProc',None):
            self.tipo = 'nfe'
        elif dicta.get('cteProc',None):
            self.tipo = 'cte'
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
    def get_cte(self):
        cte = NotaFiscal.query.filter(
            NotaFiscal.tipo == 2,
            pg_json_text_path(NotaFiscal.dados_adicionais, "chave_nf") == self.chave_acesso,
        ).first()
        if cte:
            return cte
        return None
    def get_pdf(self):
        if not self.upload:
            logger.debug("get_pdf: %s chave: %s", self.id, self.chave_acesso)

            if self.chave_acesso:
                pdf_data = Arquivei(chave_acesso=self.chave_acesso, pdf=True)
                if not pdf_data.pdf:
                    return None
                self.upload = Upload.registrar(
                    pai='NotaFiscal',
                    pai_id=self.id,
                    tipo=1,
                    filename=f'{self.chave_acesso}.pdf',
                    mimetype='application/pdf',
                    blob=pdf_data.pdf
                )
                return self.upload
 
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
    def get_cancelado(self):
        logger.debug("get_cancelado: %s id: %s chave: %s", self.tipo, self.id, self.chave_acesso)
        arquivei = Arquivei(chave_acesso=self.chave_acesso,cancelamento=True)
        if arquivei.cancelada:
            nf = NotaFiscal.query.get(self.id)
            nf.status_processamento = 'cancelada'
            nf.save()
            return True
        return False
    def importar_arquivei(data_inicial,data_final,tipo='nfe',logs=None):
        notas = Arquivei(data_inicial=data_inicial, data_final=data_final,tipo=tipo)
        #print(f'notas: {len(notas.datas)}')
        #print(f'notas.datas: {notas}')
        total = len(notas.datas)
        logs={
            'tipo': tipo,
            'total': 0,
            'existente': 0,
            'inserido': 0,
            'erro': 0,
            'erros': [],
            'mensagem': [],
            'existentes': [],
            'inseridos': [],
        }
        logs['total'] = total
        i=0
        notasn = []
        if total > 0:
            for data in notas.datas:
                nf = NotaFiscal(data=data)

                if nf.logs['erro']:
                    logs['erro'] += 1
                    logs['erros'].append(nf.logs['erro'])
                if nf.logs['mensagem']:
                    logs['mensagem'].append(nf.logs['mensagem'])
                if nf.logs['existentes']:
                    logs['existente'] += 1
                    logs['existentes'].append(nf.logs)
                if nf.logs['inseridos']:
                    logs['inserido'] += 1
                    logs['inseridos'].append(nf.logs)
                notasn.append(nf)
            i+=1
        for nf in notasn:
            logger.debug("nf: %s tipo: %s", nf.id, nf.tipo)
            if nf.tipo != 3 and nf.tipo != 'nfse':
                if not nf.get_cancelado():
                    nf.get_pdf()
                else:
                    logger.debug("nf cancelada: %s chave: %s tipo: %s", nf.id, nf.chave_acesso, nf.tipo)
        #print(f'logs: {logs}')
        return logs
    def processar_cte(self):
        from .services.processamento_documento import executar_processamento_cte
        return executar_processamento_cte(self)

    def processar_nfse(self):
        from .services.processamento_documento import executar_processamento_nfse
        return executar_processamento_nfse(self)

    def processar_nfe(self):
        from .services.processamento_documento import executar_processamento_nfe
        return executar_processamento_nfe(self)

    def extrair_dados_xml_cte(self):
        from .parsing.xml_extracao import extrair_dados_xml_cte as _extrair_cte
        return _extrair_cte(self.xml_data)

    def extrair_dados_xml_nfe(self):
        from .parsing.xml_extracao import extrair_dados_xml_nfe as _extrair_nfe
        return _extrair_nfe(self.xml_data)

    def extrair_dados_xml_nfse(self):
        from .parsing.xml_extracao import extrair_dados_xml_nfse as _extrair_nfse
        return _extrair_nfse(self.xml_data)

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
                    logger.debug("item_anterior: %s", item_anterior.material.nome)
                    if comparar_unidades(item_anterior.unidade, item.unidade):
                        item.fator_conversao_aplicado = item_anterior.fator_conversao_aplicado
                        item.material_id = item_anterior.material_id
                        item.save()
                        db.session.commit()
                        db.session.refresh(item)
                        itens_vinculados += 1
                else:
                    logger.debug("item %s não vinculado a um material do sistema", item.id)
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
    importado_estoque = db.Column(SmallInteger, nullable=False, default=0)
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
                    NotaFiscalItem.importado_estoque == 1
                ).order_by(NotaFiscalItem.data_importacao_estoque.asc()).first()
                
                if item_anterior and item_anterior.material_id:
                    return item_anterior
            
            # Prioridade 2: Buscar por correspondência exata na descrição
            if self.descricao:
                item_anterior = NotaFiscalItem.query.filter(
                    NotaFiscalItem.descricao == self.descricao,
                    NotaFiscalItem.material_id.isnot(None),
                    NotaFiscalItem.importado_estoque == 1
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
            logger.warning("erro ao vincular: %s", e)
            return False, e
    def vincular_e_importar_estoque_todos(self,usuario_id=None, centro_custo_id=None, observacao=None):

        inicio = datetime.now()    
        itens = NotaFiscalItem.query.\
            join(NotaFiscal, NotaFiscalItem.nf_id == NotaFiscal.id).filter(
                            NotaFiscal.status_processamento!='cancelada',
                            NotaFiscalItem.codigo.like(f'%{self.codigo}%'),
                            NotaFiscalItem.descricao.like(f'%{self.descricao}%'),
                            NotaFiscalItem.nota_fiscal.has(NotaFiscal.cnpj_emitente == self.nota_fiscal.cnpj_emitente),
                            NotaFiscalItem.unidade.like(f'%{self.unidade}%')).all()
        logger.debug("itens a ser processados: %s", len(itens))
       
        logger.debug("material_id: %s", self.material_id)
        logger.debug("fator_conversao_aplicado: %s", self.fator_conversao_aplicado)
        
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
                logger.debug("importar_para_estoque_automatico: %s", item.id)
                try:
                    sucesso, mensagem, estatisticas_item = item.importar_para_estoque_automatico(usuario_id=usuario_id, centro_custo_id=centro_custo_id, observacao=observacao)
                except Exception as e:
                    logger.warning("erro ao importar item %s: %s", item.id, e)
                    import traceback
                    traceback.print_exc()
                    logger.warning("Erro ao importar item %s: %s", item.id, str(e))
                    item.estatisticas['importacao']['errosn'] += 1
                    item.estatisticas['importacao']['erros'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id)+':'+str(e))
                if sucesso:
                    logger.debug("item %s importado com sucesso", item.id)
                    item.estatisticas['importacao']['importados'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id))
                    item.estatisticas['importacao']['importadosn'] += 1
                else:
                    item.estatisticas['importacao']['errosn'] += 1

                    item.estatisticas['importacao']['erros'].append('nf:'+str(item.nota_fiscal.id)+':item:'+str(item.id)+':'+str(mensagem))

        fim = datetime.now()
        logger.debug("tempo de execucao vincular_e_importar_estoque_todos: %s", fim - inicio)
        
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
            logger.debug("Não há movimentações determinadas")
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
        
        logger.debug("resultados: %s", resultados)
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
                logger.debug("Criando novo estoque para o material %s", self.material_id)

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
                logger.debug("Estoque encontrado para o material %s", self.material_id)
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
            self.importado_estoque = 1
            self.data_importacao_estoque = datetime.now()
            self.usuario_importacao_id = usuario_id
            self.status_importacao = 'importado'
            self.ultima_tentativa_importacao = datetime.now()
            self.tentativas_importacao += 1
            self.movimentacao_estoque_id = movimentacao.id
            self.save()
            fim = datetime.now()
            logger.debug("tempo de execucao importar_para_estoque: %s", fim - inicio)
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