/**
 * Comportamento dos modais de avaliação PLR (nova e editar).
 * Depende de window.CRITERIOS_PADRAO_PLR definido no template.
 */
(function() {
    var criteriosPadrao = window.CRITERIOS_PADRAO_PLR || [
        { tipo: 'Assiduidade', valor: '', peso: 0.30 },
        { tipo: 'Zero Acidente', valor: '', peso: 0.15 },
        { tipo: 'Segurança, Limpeza, Organização', valor: '', peso: 0.25 },
        { tipo: 'Prazo', valor: '', peso: 0.30 }
    ];

    function buildAvaliacaoJsonForForm(form) {
        var container = form.querySelector('.avaliacao-criterios-container');
        var input = form.querySelector('.avaliacao-json-input');
        if (!container || !input) return;
        var rows = container.querySelectorAll('.criterio-row');
        var arr = [];
        rows.forEach(function(row) {
            var tipo = row.querySelector('.criterio-tipo');
            var valorEl = row.querySelector('.criterio-valor');
            var pesoEl = row.querySelector('.criterio-peso');
            if (!tipo) return;
            var valor = valorEl && valorEl.value !== '' ? parseFloat(valorEl.value) : null;
            var peso = pesoEl && pesoEl.value !== '' ? parseFloat(pesoEl.value) / 100 : null;
            arr.push({
                tipo: tipo.value || 'Critério',
                valor: valor !== null ? valor : 0,
                peso: peso
            });
        });
        input.value = JSON.stringify(arr);
    }

    function addRowToContainer(container, item) {
        item = item || {};
        var pesoPct = item.peso != null ? Math.round(item.peso * 100) : '';
        var html = '<div class="row g-2 mb-2 criterio-row align-items-center">' +
            '<div class="col-md-4"><input type="text" class="form-control criterio-tipo" placeholder="Ex: Assiduidade" value="' + (item.tipo || '') + '"></div>' +
            '<div class="col-md-2"><input type="number" step="0.01" min="0" max="100" class="form-control criterio-peso" placeholder="Peso %" value="' + pesoPct + '"></div>' +
            '<div class="col-md-3"><input type="number" step="0.01" min="0" max="10" class="form-control criterio-valor" placeholder="Nota 0-10" value="' + (item.valor !== undefined && item.valor !== '' ? item.valor : '') + '"></div>' +
            '<div class="col-md-2"><button type="button" class="btn btn-outline-danger btn-sm btn-remover-criterio"><i class="fas fa-minus"></i></button></div></div>';
        container.insertAdjacentHTML('beforeend', html);
    }

    document.addEventListener('submit', function(e) {
        var form = e.target && e.target.classList && e.target.classList.contains('form-avaliacao-plr') && e.target;
        if (form) {
            buildAvaliacaoJsonForForm(form);
        }
    });

    document.addEventListener('click', function(e) {
        var modal = e.target.closest('.modal');
        if (!modal) return;

        if (e.target.closest('.btn-criterios-padrao')) {
            var container = modal.querySelector('.avaliacao-criterios-container');
            if (container) {
                container.innerHTML = '';
                criteriosPadrao.forEach(function(c) { addRowToContainer(container, c); });
            }
            e.preventDefault();
            return;
        }

        if (e.target.closest('.btn-add-criterio')) {
            var container = modal.querySelector('.avaliacao-criterios-container');
            if (container) addRowToContainer(container, {});
            e.preventDefault();
            return;
        }

        if (e.target.closest('.btn-remover-criterio')) {
            var row = e.target.closest('.criterio-row');
            if (row) row.remove();
            e.preventDefault();
        }
    });
})();
