/* =========================================================
   MAIN.JS - Arquivo Mestre (Estado Global + Filtros + Chat)
   ========================================================= */

import { renderEditais } from './render.js';

// --- ESTADO GLOBAL ---
let editaisOriginais = []; // Fonte da verdade (imutável após load)

let botIsTyping = false;
let chatState = null;

// --- ELEMENTOS DOM ---
const container = document.getElementById('editais-container');
const searchInput = document.getElementById('search');
const dateStartInput = document.getElementById('date-start');
const dateEndInput = document.getElementById('date-end');
const clearFilterBtn = document.querySelector('.clear-filter-btn') || document.getElementById('clear-date-filter');

// Sidebar & Modal Elements
const modalOverlay = document.getElementById('modal-overlay');
const modalContentContainer = document.getElementById('modal-content-container');
const modalCloseBtn = document.getElementById('modal-close-btn');
const sidebar = document.querySelector('.filter-sidebar-compact');
const toggleBtn = document.getElementById('filter-toggle-btn');
const sidebarOverlay = document.querySelector('.sidebar-overlay');

// Chat Elements
const chatInput = document.getElementById('chat-input');
const sendButton = document.getElementById('send-button');
const messageContainer = document.getElementById('chatbot-messages');
const chatWrapper = document.getElementById('chatbot-wrapper');
const chatButton = document.querySelector('.e-contact-buttons__chat-button');

// =========================
// INICIALIZAÇÃO
// =========================
document.addEventListener('DOMContentLoaded', init);

async function init() {
    await loadEditais();
    
    // Gera as opções de filtro dinamicamente com base nos dados carregados
    generateDynamicFilters();

    setupGlobalEvents();
    
    // Renderização inicial
    aplicarFiltrosEBusca();

    // DEEP LINKING: Checa se tem ?id=X na URL
    const urlParams = new URLSearchParams(window.location.search);
    const editalId = urlParams.get('id');
    if (editalId) {
        const targetEdital = editaisOriginais.find(e => e.id == editalId);
        if (targetEdital) openModal(targetEdital);
    }
}

// =========================
// CARREGAMENTO DE DADOS
// =========================
async function loadEditais() {
    try {
        const res = await fetch('http://127.0.0.1:8000/editais');
        const apiData = await res.json();
        // Normaliza e salva no estado global
        editaisOriginais = apiData.map(normalizeEdital);
    } catch (e) {
        console.error('Erro ao carregar editais:', e);
        container.innerHTML = '<p class="no-results">Erro ao carregar dados. Tente atualizar a página.</p>';
    }
}

function normalizeEdital(api) {
    const data = typeof api.json_data === 'string' ? JSON.parse(api.json_data) : (api.json_data || {});
    const arquivos = typeof api.arquivos_json === 'string' ? JSON.parse(api.arquivos_json) : (api.arquivos_json || []);
    
    return {
        id: api.id,
        titulo: data.titulo || api.titulo || 'Sem título',
        descricao: data.objetivo || data.descricao || 'Sem descrição',
        publico_alvo: data.publico_alvo || '',
        icone: data.icone_instituicao || null,
        instituicao: data.instituicao || '',
        estado: data.estado || 'BR',
        area: data.area || (Array.isArray(data.tags) && data.tags.length ? data.tags[0] : 'Geral'),
        apoio: data.apoio || 'Não informado',
        tipo: data.tipo || 'Não informado',
        valor_total: data.valor_total || '',
        // Padroniza datas para YYYY-MM-DD para facilitar comparação
        data_fechamento: api.data_final_submissao || data.data_final_submissao || null,
        data_abertura: data.data_abertura || null,
        tags: data.tags || [],
        arquivos: arquivos,
        share_link: api.share_link || ''
    };
}

// =========================
// GERAÇÃO DINÂMICA DE FILTROS
// =========================
function generateDynamicFilters() {
    // Mapeamento: propriedade do objeto Edital -> data-filter-type no HTML
    // Adicionado 'categoria' como alias para 'area' para garantir compatibilidade
    const filterMap = [
        { key: 'estado', type: 'estado' },
        { key: 'area', type: 'area' },
        { key: 'area', type: 'categoria' }, 
        { key: 'instituicao', type: 'instituicao' },
        { key: 'apoio', type: 'apoio' },
        { key: 'tipo', type: 'tipo' }
    ];

    filterMap.forEach(filter => {
        // Tenta encontrar o container de opções dentro da sidebar
        const wrapper = document.querySelector(`.filter-sidebar-compact [data-filter-type="${filter.type}"] .filter-options-wrapper`);
        
        if (wrapper) {
            // 1. Extrai valores únicos
            // Filtra valores vazios ou nulos e ordena alfabeticamente
            const values = [...new Set(editaisOriginais.map(e => e[filter.key]))]
                .filter(v => v && v.trim() !== '')
                .sort();

            // 2. Limpa o HTML atual (loading ou estático)
            wrapper.innerHTML = '';

            // 3. Cria as checkboxes
            if (values.length === 0) {
                wrapper.innerHTML = '<span style="font-size:0.8rem; opacity:0.6; padding:5px;">Nenhuma opção</span>';
            } else {
                values.forEach(val => {
                    const label = document.createElement('label');
                    label.style.display = 'flex';
                    label.style.alignItems = 'center';
                    label.style.gap = '8px';
                    label.style.padding = '4px 0';
                    label.style.cursor = 'pointer';
                    
                    const input = document.createElement('input');
                    input.type = 'checkbox';
                    input.value = val;
                    
                    const span = document.createElement('span');
                    span.innerText = val;
                    
                    label.appendChild(input);
                    label.appendChild(span);
                    wrapper.appendChild(label);
                });
            }
        }
    });
}

// =========================
// LÓGICA CENTRAL DE FILTRO (A ALMA DO SISTEMA)
// =========================
function aplicarFiltrosEBusca() {
    // Sempre começa com a lista completa (State Global)
    let resultado = [...editaisOriginais];

    // 1. BUSCA TEXTUAL
    const termo = searchInput ? searchInput.value.toLowerCase().trim() : '';
    if (termo) {
        resultado = resultado.filter(edital => 
            edital.titulo.toLowerCase().includes(termo) ||
            edital.descricao.toLowerCase().includes(termo) ||
            edital.instituicao.toLowerCase().includes(termo) ||
            (edital.area && edital.area.toLowerCase().includes(termo)) || // Adicionado busca por categoria
            (edital.tags && edital.tags.some(tag => tag.toLowerCase().includes(termo)))
        );
    }

    // 2. CHECKBOXES (Categorias, Estados, Instituições, etc)
    // Helper para pegar valores marcados dentro de um grupo específico
    const getChecked = (tipo) => 
        Array.from(document.querySelectorAll(`.filter-sidebar-compact [data-filter-type="${tipo}"] input:checked`))
             .map(cb => cb.value);

    const estados = getChecked('estado');
    // Coleta tanto 'area' quanto 'categoria' para ser robusto
    const areas = [...getChecked('area'), ...getChecked('categoria')];
    const instituicoes = getChecked('instituicao'); 
    const apoios = getChecked('apoio');
    const tipos = getChecked('tipo');

    if (estados.length) resultado = resultado.filter(e => estados.includes(e.estado));
    if (areas.length) resultado = resultado.filter(e => areas.includes(e.area));
    if (instituicoes.length) resultado = resultado.filter(e => instituicoes.includes(e.instituicao));
    if (apoios.length) resultado = resultado.filter(e => apoios.includes(e.apoio));
    if (tipos.length) resultado = resultado.filter(e => tipos.includes(e.tipo));

    // 3. DATAS
    const inicio = dateStartInput ? dateStartInput.value : '';
    const fim = dateEndInput ? dateEndInput.value : '';

    if (inicio || fim) {
        resultado = resultado.filter(e => {
            // Usa data_fechamento como principal, fallback para abertura
            const dataEdital = e.data_fechamento || e.data_abertura;
            if (!dataEdital) return false;
            
            // Comparação de string YYYY-MM-DD funciona bem aqui
            const condicaoInicio = !inicio || dataEdital >= inicio;
            const condicaoFim = !fim || dataEdital <= fim;
            
            return condicaoInicio && condicaoFim;
        });
    }

    // 4. RENDERIZAÇÃO
    renderEditais(container, resultado);
}

// =========================
// EVENT LISTENERS UNIFICADOS
// =========================
function setupGlobalEvents() {
    // Busca Instantânea
    if (searchInput) {
        searchInput.addEventListener('input', aplicarFiltrosEBusca);
    }

    // EVENT DELEGATION PARA CHECKBOXES
    // Como os checkboxes são gerados dinamicamente, usamos delegação no pai (sidebar)
    if (sidebar) {
        sidebar.addEventListener('change', (e) => {
            if (e.target.matches('input[type="checkbox"]')) {
                aplicarFiltrosEBusca();
            }
        });
    }

    // Datas
    if (dateStartInput) dateStartInput.addEventListener('change', aplicarFiltrosEBusca);
    if (dateEndInput) dateEndInput.addEventListener('change', aplicarFiltrosEBusca);

    // Botão Limpar Filtros
    if (clearFilterBtn) {
        clearFilterBtn.addEventListener('click', () => {
            // Reseta inputs
            if (searchInput) searchInput.value = '';
            if (dateStartInput) dateStartInput.value = '';
            if (dateEndInput) dateEndInput.value = '';
            
            // Reseta checkboxes
            document.querySelectorAll('.filter-sidebar-compact input[type="checkbox"]').forEach(cb => {
                cb.checked = false;
            });

            // Reaplica (vai mostrar tudo)
            aplicarFiltrosEBusca();
        });
    }

    // --- UI UX: Toggles da Sidebar ---
    document.querySelectorAll('.filter-summary').forEach(summary => {
        summary.addEventListener('click', () => {
            const options = summary.nextElementSibling?.querySelector('.filter-options-compact');
            // Fallback para caso o wrapper seja direto (dependendo do HTML)
            const target = options || summary.nextElementSibling;
            
            const icon = summary.querySelector('i');
            if (target) target.classList.toggle('open');
            if (icon) {
                icon.classList.toggle('fa-chevron-right');
                icon.classList.toggle('fa-chevron-down');
            }
        });
    });

    // Mobile Sidebar Toggle
    if (toggleBtn && sidebar && sidebarOverlay) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            sidebarOverlay.classList.toggle('active');
        });
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('active');
        });
    }

    // Chatbot Toggles
    if (chatButton && chatWrapper) {
        chatButton.addEventListener('click', () => {
            chatWrapper.classList.toggle('open');
            scrollToBottom();
            if (messageContainer?.children.length === 0) {
                addMessage('Olá! Busque por um tema (ex: inovação) e eu listarei os editais disponíveis.', 'bot');
            }
        });
    }

    if (sendButton && chatInput) {
        sendButton.addEventListener('click', handleChatSend);
        chatInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleChatSend();
            }
        });
    }

    // Modal Events
    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
    if (modalOverlay) modalOverlay.addEventListener('click', e => {
        if (e.target === modalOverlay) closeModal();
    });

    // Card Click (Delegation)
    if (container) {
        container.addEventListener('click', e => {
            const card = e.target.closest('.notice-card');
            if (e.target.closest('.share-btn')) return; // Ignora se clicou no share
            if (!card) return;
            
            const edital = editaisOriginais.find(ed => ed.id.toString() === card.dataset.id);
            if (edital) openModal(edital);
        });
    }
}

// =========================
// MODAL
// =========================
function openModal(edital) {
    if (!modalOverlay || !modalContentContainer) return;

    let arquivosHtml = '';
    if (edital.arquivos && edital.arquivos.length > 0) {
        arquivosHtml = `
        <div class="attachments-section">
            <div class="attachments-summary">
                <h3>Recursos e Documentos</h3>
                <i class="fas fa-chevron-right"></i>
            </div>
            <div class="attachments-wrapper">
                <ul class="attachment-list">
                    ${edital.arquivos.map(a => `
                        <li>
                            <a href="${a.url}" target="_blank" download>
                                <i class="fas fa-link"></i> ${a.nome || 'Acessar Documento'}
                            </a>
                        </li>
                    `).join('')}
                </ul>
            </div>
        </div>`;
    } else {
        arquivosHtml = '<p style="margin-top:20px; opacity:0.7;">Nenhum documento anexado.</p>';
    }

    const shareBtnHtml = edital.share_link 
        ? `<button class="modal-share-btn" onclick="navigator.clipboard.writeText('${edital.share_link}'); alert('Link copiado!');">
             <i class="fas fa-link"></i> Copiar Link
           </button>`
        : '';

    modalContentContainer.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            ${edital.icone ? `<img src="${edital.icone}" alt="${edital.instituicao}" style="max-height:80px; margin-bottom:15px;">` : '<div></div>'}
            ${shareBtnHtml}
        </div>
        <h2>${edital.titulo}</h2>
        <p>${edital.descricao}</p>
        ${edital.publico_alvo ? `<p><strong>Público Alvo:</strong> ${edital.publico_alvo}</p>` : ''}
        ${edital.valor_total ? `<p><strong>Valor Total:</strong> ${edital.valor_total}</p>` : ''}
        <div class="modal-details">
            <div><strong>Instituição</strong><span>${edital.instituicao || 'Não informada'}</span></div>
            <div><strong>Estado</strong><span>${edital.estado}</span></div>
            <div><strong>Categoria</strong><span>${edital.area}</span></div>
            ${edital.data_fechamento ? `<div><strong>Fechamento</strong><span>${edital.data_fechamento}</span></div>` : ''}
        </div>
        ${arquivosHtml}
    `;

    // Accordion Logic inside Modal
    const summary = modalContentContainer.querySelector('.attachments-summary');
    if (summary) {
        summary.addEventListener('click', () => {
            const wrapper = summary.nextElementSibling;
            const icon = summary.querySelector('i');
            wrapper.classList.toggle('open');
            if (wrapper.classList.contains('open')) {
                icon.classList.remove('fa-chevron-right');
                icon.classList.add('fa-chevron-down');
            } else {
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-right');
            }
        });
    }

    modalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    if (modalOverlay) modalOverlay.classList.remove('open');
    document.body.style.overflow = '';
}

// =========================
// CHATBOT RAG
// =========================
function scrollToBottom() {
    if (messageContainer) setTimeout(() => messageContainer.scrollTop = messageContainer.scrollHeight, 50);
}

function addMessage(content, sender, options = null) {
    if (!messageContainer) return;
    const div = document.createElement('div');
    div.classList.add('message', sender);
    div.innerHTML = content;

    if (options?.length) {
        const optionsContainer = document.createElement('div');
        optionsContainer.style.marginTop = '10px';
        optionsContainer.style.display = 'flex';
        optionsContainer.style.flexDirection = 'column';
        optionsContainer.style.gap = '5px';
        options.forEach(opt => {
            const btn = document.createElement('button');
            btn.className = 'chat-option-btn';
            btn.innerText = opt.titulo;
            btn.onclick = () => selectEditalContext(opt.id, opt.titulo);
            optionsContainer.appendChild(btn);
        });
        div.appendChild(optionsContainer);
    }
    messageContainer.appendChild(div);
    scrollToBottom();
}

function selectEditalContext(id, titulo) {
    chatState = { id, titulo };
    document.querySelectorAll('.chat-option-btn').forEach(b => b.disabled = true);
    addMessage(`✅ Edital selecionado: <strong>${titulo}</strong>`, 'user');
    setTimeout(() => {
        addMessage(`Agora estou analisando os documentos deste edital. Digite 'sair' para voltar a buscar.`, 'bot');
    }, 500);
}

async function handleChatSend() {
    if (botIsTyping || !chatInput || !messageContainer) return;
    const userText = chatInput.value.trim();
    if (!userText) return;

    if (['sair', 'voltar'].includes(userText.toLowerCase())) {
        chatState = null;
        addMessage(userText, 'user');
        setTimeout(() => addMessage("Contexto limpo. Pode buscar por novos editais.", 'bot'), 500);
        chatInput.value = '';
        return;
    }

    botIsTyping = true;
    sendButton.disabled = true;
    addMessage(userText, 'user');
    chatInput.value = '';
    addMessage('Processando...', 'bot');

    try {
        const endpoint = chatState?.id
            ? `http://127.0.0.1:8000/chat/edital/${chatState.id}`
            : 'http://127.0.0.1:8000/chat';

        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: userText })
        });
        if (!res.ok) throw new Error('Erro na API');
        const responseData = await res.json();

        const last = messageContainer.lastChild;
        if (last && last.textContent.includes('Processando...')) last.remove();

        addMessage(responseData.reply, 'bot', responseData.options);
    } catch (err) {
        const last = messageContainer.lastChild;
        if (last && last.textContent.includes('Processando...')) last.remove();
        addMessage('⚠️ Ocorreu um erro ao processar sua mensagem.', 'bot');
    }

    botIsTyping = false;
    sendButton.disabled = false;
    scrollToBottom();
}
