from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField, MultipleFileField
from wtforms.validators import DataRequired

class NotaFiscalImportForm(FlaskForm):
    xml_zip_files = MultipleFileField(
        'Selecione um ou mais arquivos XML ou um arquivo ZIP',
        validators=[DataRequired(message="Por favor, selecione pelo menos um arquivo.")]
    )
    submit = SubmitField('Importar') 