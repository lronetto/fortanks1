import json
from datetime import datetime

from sqlalchemy.orm import relationship
from werkzeug.datastructures import FileStorage

from models.database import db
from models.upload import Upload
from models.upload.utils.imagem_filestorage import salvar_upload_imagem_filestorage

from ..constants import TABELA_MATERIAIS
from ..constants import PAI_MATERIAL, TIPO_IMAGEM_MATERIAL
from .associacao import materiais_grupos
from utils.utils import parse_dados_json_int, set_dados_json_item


class Materiais(db.Model):
    """
    Modelo para representar materiais
    """

    __tablename__ = TABELA_MATERIAIS

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    plano_conta = db.Column(db.String(30), nullable=True)
    plano_conta_id = db.Column(db.Integer, db.ForeignKey("planos_conta.id"), nullable=True)
    plano_conta_obj = relationship(
        "PlanoConta", back_populates="materiais", foreign_keys=[plano_conta_id]
    )
    ncm = db.Column(db.String(15), nullable=True)
    mascara = db.Column(db.Integer, nullable=True)

    # Referência à tabela de unidades
    unidade_id = db.Column(db.Integer, db.ForeignKey("Unidades.id"), nullable=True)

    categoria = db.Column(db.String(50), nullable=True)  # Adicionando campo categoria
    formula_calculo = db.Column(db.String(500), nullable=True)  # Fórmula universal para cálculo de quantidade
    dados_adicionais = db.Column(db.Text, nullable=True)  # Dados adicionais em formato JSON
    criado_em = db.Column(db.DateTime, default=datetime.now)

    # unidade = db.relationship('Unidade', back_populates='materiais', foreign_keys=[unidade_id])
    # Relacionamento com itens de solicitação
    solicitacoes_itens = db.relationship("SolicitacoesItens", back_populates="material")
    # Renomeado para evitar conflito com o campo string 'unidade' e para maior clareza
    unidade_obj = db.relationship("Unidades", back_populates="materiais", foreign_keys=[unidade_id])

    # Relacionamento com grupos de materiais
    grupos = relationship("MateriaisGrupos", secondary=materiais_grupos, back_populates="materiais")

    @classmethod
    def criar_desde_formulario(cls, **kwargs):
        """Monta uma instância nova a partir de campos de formulário (sem persistir)."""
        from ..services.cadastro_edicao import construir_material_novo

        return construir_material_novo(**kwargs)

    def aplicar_edicao_desde_formulario(self, **kwargs):
        """Atualiza campos e JSON auxiliar conforme formulário de edição (sem commit)."""
        from ..services.cadastro_edicao import aplicar_edicao_formulario

        aplicar_edicao_formulario(self, **kwargs)

    def excluir_apos_validar_vinculos(self) -> str:
        """Valida vínculos, exclui e devolve mensagem de sucesso; ``ValueError`` se bloqueado."""
        from ..services.exclusao import excluir_material_validando_vinculos

        return excluir_material_validando_vinculos(self)

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            "unidade": self.unidade_obj.nome if self.unidade_obj else None,
            "unidade_id": self.unidade_id,
        }

    def save(self):
        """
        Salva o material no banco de dados
        """
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """
        Remove o material do banco de dados
        """
        db.session.delete(self)
        db.session.commit()

    @property
    def data_criacao(self):
        """
        Retorna a data de criação do material (para compatibilidade com código existente)
        """
        return self.criado_em
    def set_imagem_upload_id(self, upload_id: int):
        self.dados_adicionais = set_dados_json_item(self.dados_adicionais, "imagem_upload_id", upload_id)
    
    def set_imagem_upload(self, file_storage: FileStorage):
        img_id = salvar_upload_imagem_filestorage(
            file_storage,
            pai=PAI_MATERIAL,
            pai_id=self.id,
            tipo=TIPO_IMAGEM_MATERIAL,
            prefixo_arquivo=f"mat{self.id}_",
            nome_sem_arquivo="clipboard",
            nome_seguro_fallback="imagem",
            )       
        if img_id:
            self.set_imagem_upload_id(img_id)
            self.save()
    def remover_imagem_upload(self):
        img_id = self.get_imagem_upload_id()
        if img_id:
            u = Upload.query.get(img_id)
            if u and u.pai == PAI_MATERIAL and u.pai_id == self.id and u.tipo == TIPO_IMAGEM_MATERIAL:
                u.delete()
                self.set_imagem_upload_id(0)
                self.save()
    @property
    def imagem_upload_id(self):
        """ID em Upload (tipo imagem material) gravado em dados_adicionais."""
        return parse_dados_json_int(self.dados_adicionais, "imagem_upload_id")

    def __repr__(self):
        """
        Representação em string do material
        """
        return f"<Material {self.id} - {self.nome}>"

    def get_unidade_nome(self):
        """
        Retorna o nome da unidade do material
        """
        # Se tiver unidade_obj, usa o nome dela
        if hasattr(self, "unidade_obj") and self.unidade_obj:
            return self.unidade_obj.nome
        # Senão, usa o campo string unidade
        return self.unidade

    def tem_conversoes(self):
        """
        Verifica se o material possui conversões de unidades
        """
        # Se não tiver unidade definida, não tem conversões
        if not self.unidade_id and not self.unidade:
            return False

        # Verifica se tem conversões específicas para este material
        return len(getattr(self, "conversoes_unidade", [])) > 0

    def get_valor_unitario(self):
        """
        Retorna o valor unitário do material
        """
        from models.nota_fiscal.services.material_precos import obter_valor_unitario_material

        return obter_valor_unitario_material(self.id)

    def calcular_quantidade(
        self,
        quantidade_total,
        placas_normais,
        placas_fecho,
        quantidade_bainhas,
        altura_total=None,
        sistema=None,
    ):
        """
        Calcula a quantidade do material baseado na fórmula universal de cálculo
        A fórmula é universal (cadastrada no material), mas usa os dados específicos do tanque

        Variáveis disponíveis na fórmula:
        - quantidade_total: quantidade de tanques
        - placas_normais: quantidade de placas normais
        - placas_fecho: quantidade de placas de fecho
        - quantidade_bainhas: quantidade de bainhas
        - altura_total: altura total do tanque
        - sistema: sistema do tanque (SC-10, SC-14, SR-06)
        """
        if not self.formula_calculo:
            return 1.0

        try:
            # Criar um contexto seguro para eval
            contexto = {
                "quantidade_total": float(quantidade_total or 1),
                "placas_normais": float(placas_normais or 0),
                "placas_fecho": float(placas_fecho or 0),
                "quantidade_bainhas": float(quantidade_bainhas or 0),
                "altura_total": float(altura_total or 0),
                "sistema": sistema or "",
            }

            # Substituir variáveis na fórmula por valores seguros
            formula = self.formula_calculo.strip()

            # Avaliar a fórmula de forma segura
            resultado = eval(formula, {"__builtins__": {}}, contexto)

            return float(resultado) if resultado else 1.0
        except Exception as e:
            # Em caso de erro, retornar 1.0 como padrão
            print(f"Erro ao calcular fórmula para material {self.id}: {str(e)}")
            return 1.0
