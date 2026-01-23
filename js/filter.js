import { renderEditais } from './render.js';

// Variáveis internas para manter o estado
let allEditais = [];
let cardsContainer = null;
let searchField = null;
let dateStartInput = null;
let dateEndInput = null;

// Função principal de inicialização que é chamada pelo main.js
export function initFilters(editais, container, searchInput) {
    allEditais = editais;
    cardsContainer = container;
    searchField = searchInput;
    
    // Identifica os inputs de data no DOM
    dateStartInput = document.getElementById('date-start') || document.querySelector('input[type="date"][name="start"]');
    dateEndInput = document.getElementById('date-end') || document.querySelector('input[type="date"][name="end"]');
    
    // 1. Aplica filtros iniciais (todos)
    applyFilters(); 

    // 2. Adiciona os Listeners
    searchField.addEventListener('input', applyFilters);
    
    // Listeners para datas (se os inputs existirem)
    if (dateStartInput) dateStartInput.addEventListener('change', applyFilters);
    if (dateEndInput) dateEndInput.addEventListener('change', applyFilters);
    
    // Configura listeners para os checkboxes
    document.querySelectorAll('.filter-sidebar-compact input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', applyFilters);
    });
    
    // Configura listeners para a expansão/recolhimento da sidebar
    const filterSummaries = document.querySelectorAll('.filter-summary');
    filterSummaries.forEach(summary => {
        summary.addEventListener('click', () => {
            const options = summary.nextElementSibling;
            const icon = summary.querySelector('i');
            
            options.classList.toggle('open');
            
            if (options.classList.contains('open')) {
                icon.classList.remove('fa-chevron-right');
                icon.classList.add('fa-chevron-down');
            } else {
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-right');
            }
        });
    });
}

function applyFilters() {
    const query = searchField.value.trim().toLowerCase();
    
    // ----------------------------------------------------
    // 1. CAPTURA DOS FILTROS CHECKBOX
    // ----------------------------------------------------
    const checkedCheckboxes = Array.from(document.querySelectorAll('.filter-sidebar-compact input[type="checkbox"]:checked'));
    const estados = checkedCheckboxes.filter(cb => cb.closest('[data-filter-type="estado"]')).map(cb => cb.value);
    const categorias = checkedCheckboxes.filter(cb => cb.closest('[data-filter-type="area"]')).map(cb => cb.value);
    const apoios = checkedCheckboxes.filter(cb => cb.closest('[data-filter-type="apoio"]')).map(cb => cb.value);
    const tipos = checkedCheckboxes.filter(cb => cb.closest('[data-filter-type="tipo"]')).map(cb => cb.value);

    // ----------------------------------------------------
    // 2. CAPTURA E PARSE DAS DATAS
    // ----------------------------------------------------
    const startDateValue = dateStartInput ? dateStartInput.value : '';
    const endDateValue = dateEndInput ? dateEndInput.value : '';

    // Função para converter data (dd/mm/yyyy ou yyyy-mm-dd) para objeto Date
    const parseDate = (dateString) => {
        if (!dateString) return null;
        let d = dateString.includes('-') ? dateString.split('-') : dateString.split('/');
        // Se for yyyy-mm-dd (input date), d é [yyyy, mm, dd]. Se for dd/mm/yyyy, d é [dd, mm, yyyy]
        
        // Tentamos criar a data, garantindo que o JS entenda
        if (dateString.includes('-')) { 
             // Formato yyyy-mm-dd (do input date)
             return new Date(d[0], d[1] - 1, d[2]);
        } else if (d.length === 3) { 
             // Formato dd/mm/yyyy (do JSON, se for o caso)
             return new Date(d[2], d[1] - 1, d[0]);
        }
        return null;
    };
    
    // ----------------------------------------------------
    // 3. APLICAÇÃO DOS FILTROS (ORDEM CORRETA)
    // ----------------------------------------------------
    let filtered = allEditais;
    
    // A. BUSCA TEXTUAL (Fuzzy ou Padrão)
    if (query) {
        if (typeof fuse !== 'undefined' && fuse) {
            // Usa o Fuse.js para buscar com tolerância a erros ortográficos se estiver definido
            const results = fuse.search(query);
            filtered = results.map(result => result.item);
        } else {
            // Fallback para busca padrão se o Fuse não estiver inicializado
            filtered = filtered.filter(e => 
                e.titulo.toLowerCase().includes(query) || 
                e.descricao.toLowerCase().includes(query)
            );
        }
    }
    
    // B. FILTROS DE CHECKBOX (Aplicados sobre o resultado da busca ou todos os editais)
    if (estados.length) filtered = filtered.filter(e => estados.includes(e.estado));
    if (categorias.length) filtered = filtered.filter(e => categorias.includes(e.area));
    if (apoios.length) filtered = filtered.filter(e => apoios.includes(e.apoio));
    if (tipos.length) filtered = filtered.filter(e => tipos.includes(e.tipo));

    // C. FILTRO POR DATA (Aplicado por último)
    if (startDateValue || endDateValue) {
        const startDate = parseDate(startDateValue);
        // A data final deve ser o dia exato de fim (a função parseDate já lida com o fuso)
        const endDate = parseDate(endDateValue); 

        filtered = filtered.filter(edital => {
            // Usamos a data de fechamento, mas mantendo fallback para data_abertura se fechamento não existir
            const editalDate = parseDate(edital.data_fechamento || edital.data_abertura); 

            if (!editalDate) return false; 

            // Compara a data do edital com o início e o fim
            const afterStart = !startDate || editalDate >= startDate;
            // Para a data final, somamos um dia para incluir o dia exato selecionado
            const beforeEnd = !endDate || editalDate < new Date(endDate.getTime() + 86400000); 

            return afterStart && beforeEnd;
        });
    }

    renderEditais(cardsContainer, filtered, isAdminLogged());
    
}