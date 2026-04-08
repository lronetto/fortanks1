from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FloatField, DateField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Optional, NumberRange

class EstoqueForm(FlaskForm):
    material_id = SelectField('Material', coerce=int, validators=[DataRequired()])
    quantidade = FloatField('Quantidade', validators=[Optional(), NumberRange(min=0)])
    quantidade_minima = FloatField('Quantidade Mínima', validators=[Optional(), NumberRange(min=0)])
    quantidade_maxima = FloatField('Quantidade Máxima', validators=[Optional(), NumberRange(min=0)])
    lote = StringField('Lote')
    data_validade = DateField('Data de Validade', validators=[Optional()])

class MovimentacaoEstoqueForm(FlaskForm):
    estoque_id = SelectField('Item', coerce=int, validators=[DataRequired()])
    tipo_movimento = SelectField('Tipo de Movimento', choices=[
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
        ('ajuste', 'Ajuste')
    ], validators=[DataRequired()])
    quantidade = FloatField('Quantidade', validators=[DataRequired(), NumberRange(min=0)])
    observacao = StringField('Observação')

class InventarioEstoqueForm(FlaskForm):
    tipo_inventario = SelectField('Tipo de Inventário', choices=[
        ('Completo', 'Completo'),
        ('Parcial', 'Parcial')
    ], validators=[DataRequired()])
    localizacao = SelectField('Localização', choices=[], validators=[Optional()])
    observacoes = StringField('Observações')

class ItemInventarioForm(FlaskForm):
    quantidade_contada = FloatField('Quantidade Contada', validators=[Optional(), NumberRange(min=0)])
    observacoes = StringField('Observações')

class FiltroEstoqueForm(FlaskForm):
    tipo_item = SelectField('Tipo de Item', choices=[
        ('todos', 'Todos'),
        ('material', 'Material'),
        ('produto_composto', 'Produto composto'),
        ('epi', 'EPI')
    ])
    status_estoque = SelectField('Status do Estoque', choices=[
        ('todos', 'Todos'),
        ('normal', 'Normal'),
        ('critico', 'Crítico'),
        ('esgotado', 'Esgotado'),
        ('excesso', 'Excesso')
    ])
    localizacao = SelectField('Localização', choices=[], validators=[Optional()])
    termo_busca = StringField('Buscar')
    ignorar_localizacoes = BooleanField('Agrupar por Item (Ignorar Localizações)', default=False) 