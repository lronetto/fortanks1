// Funções utilitárias para o sistema

// Formatar valores monetários
function formatarMoeda(valor) {
    if (!valor) return 'R$ 0,00';

    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

// Formatar data
function formatarData(data) {
    if (!data) return '';

    const dataObj = new Date(data);
    return new Intl.DateTimeFormat('pt-BR').format(dataObj);
}

// Formatar data e hora
function formatarDataHora(data) {
    if (!data) return '';

    const dataObj = new Date(data);
    return new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short'
    }).format(dataObj);
}

// Validar formulário
function validarFormulario(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;

    let isValid = true;
    const campos = form.querySelectorAll('[required]');

    campos.forEach(campo => {
        if (!campo.value.trim()) {
            campo.classList.add('is-invalid');
            isValid = false;
        } else {
            campo.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Máscara para campos monetários
function aplicarMascaraMoeda(input) {
    input.addEventListener('input', function (e) {
        let value = e.target.value;

        // Remove tudo que não é número
        value = value.replace(/\D/g, '');

        // Converte para número e formata
        value = (parseInt(value) / 100).toFixed(2);

        // Formata com separadores
        value = value.replace('.', ',');
        value = value.replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1.');

        e.target.value = 'R$ ' + value;
    });
}

// Máscara para campos de data
function aplicarMascaraData(input) {
    input.addEventListener('input', function (e) {
        let value = e.target.value;

        // Remove tudo que não é número
        value = value.replace(/\D/g, '');

        // Adiciona as barras
        if (value.length > 2) {
            value = value.substring(0, 2) + '/' + value.substring(2);
        }
        if (value.length > 5) {
            value = value.substring(0, 5) + '/' + value.substring(5, 9);
        }

        e.target.value = value;
    });
}

// Confirmar exclusão
function confirmarExclusao(formId, mensagem = 'Tem certeza que deseja excluir este item?') {
    const form = document.getElementById(formId);
    if (!form) return;

    form.addEventListener('submit', function (e) {
        if (!confirm(mensagem)) {
            e.preventDefault();
        }
    });
}

// Inicializar tooltips do Bootstrap
function inicializarTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Inicializar popovers do Bootstrap
function inicializarPopovers() {
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
}

// Inicializar máscaras nos campos
function inicializarMascaras() {
    // Máscaras para campos monetários
    document.querySelectorAll('.mascara-moeda').forEach(input => {
        aplicarMascaraMoeda(input);
    });

    // Máscaras para campos de data
    document.querySelectorAll('.mascara-data').forEach(input => {
        aplicarMascaraData(input);
    });
}

// Inicializar confirmações de exclusão
function inicializarConfirmacoes() {
    document.querySelectorAll('.form-excluir').forEach(form => {
        confirmarExclusao(form.id);
    });
}

// Inicializar quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', function () {
    inicializarTooltips();
    inicializarPopovers();
    inicializarMascaras();
    inicializarConfirmacoes();
}); 