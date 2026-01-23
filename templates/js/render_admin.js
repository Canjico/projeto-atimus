// ==========================
// render_admin.js (Visualização em Cards + Modal de Edição + Share)
// ==========================

const token = localStorage.getItem("token");

if (!token) {
    window.location.href = "admin_login.html";
}

const modalOverlay = document.getElementById('admin-modal-overlay');
const modalCloseBtn = document.getElementById('admin-modal-close');
const btnCancelar = document.getElementById('btn-cancelar');
const form = document.getElementById('edital-form');

function openModal() {
    modalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    modalOverlay.classList.remove('open');
    document.body.style.overflow = '';
    form.reset();
    document.getElementById('edital-id').value = "";
}

if(modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
if(btnCancelar) btnCancelar.addEventListener('click', closeModal);
if(modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeModal();
    });
}

export async function carregarEditais() {
    try {
        const res = await fetch("http://127.0.0.1:8000/editais", {
            headers: { "Authorization": "Bearer " + token }
        });

        if (!res.ok) throw new Error("Erro ao carregar editais");
        
        const rawEditais = await res.json();
        const editais = rawEditais.map(normalizeEdital);

        const container = document.getElementById("editais-container");
        container.innerHTML = "";

        editais.forEach(edital => {
            const card = document.createElement("div");
            card.classList.add("notice-card");

            const tagsHtml = `
                ${edital.area ? `<span class="tag tag-area">${edital.area}</span>` : ''}
                ${edital.estado ? `<span class="tag tag-estado">${edital.estado}</span>` : ''}
            `;

            // Botão Share Admin
            const shareButton = edital.share_link 
                ? `<button class="share-btn" title="Copiar Link" onclick="navigator.clipboard.writeText('${edital.share_link}'); alert('Link copiado!'); event.stopPropagation();">
                        <i class="fas fa-share-alt"></i>
                   </button>` 
                : '';

            card.innerHTML = `
                <div style="display:flex; justify-content:flex-end; margin-bottom:5px;">
                    ${shareButton}
                </div>
                <h3>${edital.titulo}</h3>
                <p class="description">${edital.descricao}</p>
                <div class="details">
                    <p><strong>Limite:</strong> ${edital.data_fechamento || 'N/A'}</p>
                </div>
                <div class="tags">${tagsHtml}</div>
                <div style="margin-top:auto; padding-top:10px; border-top:1px solid rgba(255,255,255,0.1);">
                    <button class="admin-card-btn" onclick="window.prepararEdicao(${edital.id})">
                        <i class="fas fa-edit"></i> Editar
                    </button>
                </div>
            `;
            
            container.appendChild(card);
        });

        window.allEditais = editais;

    } catch (err) {
        console.error(err);
        alert("Erro ao carregar lista: " + err.message);
    }
}

// Normalização Admin
function normalizeEdital(api) {
    const data = (typeof api.json_data === 'string') ? JSON.parse(api.json_data) : (api.json_data || {});
    const arquivos = (typeof api.arquivos_json === 'string') ? JSON.parse(api.arquivos_json) : (api.arquivos_json || []);

    return {
        id: api.id,
        titulo: data.titulo || api.titulo || 'Sem Título',
        descricao: data.objetivo || data.descricao || '',
        estado: data.estado || 'BR',
        area: data.area || 'Geral',
        apoio: data.apoio || '',
        tipo: data.tipo || '',
        data_fechamento: data.data_final_submissao || api.data_final_submissao,
        valor_total: data.valor_total,
        temas: data.tags || [],
        arquivos: arquivos, 
        share_link: api.share_link || ''
    };
}

window.prepararEdicao = function(id) {
    const edital = window.allEditais.find(e => e.id === id);
    if (!edital) return;

    document.getElementById('modal-title').innerText = "Editar Edital #" + id;
    document.getElementById('edital-id').value = edital.id;
    
    document.getElementById('edit-titulo').value = edital.titulo;
    document.getElementById('edit-descricao').value = edital.descricao;
    document.getElementById('edit-estado').value = edital.estado;
    document.getElementById('edit-area').value = edital.area;
    document.getElementById('edit-apoio').value = edital.apoio;
    document.getElementById('edit-tipo').value = edital.tipo;
    document.getElementById('edit-data').value = edital.data_fechamento || '';
    document.getElementById('edit-valor').value = edital.valor_total || '';
    
    const pdfUrl = (edital.arquivos && edital.arquivos[0]) ? edital.arquivos[0].url : '';
    document.getElementById('edit-pdf').value = pdfUrl;

    document.getElementById('edit-tags').value = (edital.temas || []).join(', ');

    openModal();
}

window.abrirModalCriacao = function() {
    document.getElementById('modal-title').innerText = "Novo Edital";
    form.reset();
    document.getElementById('edital-id').value = ""; 
    openModal();
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('edital-id').value;
    const isUpdate = !!id;

    const dados = {
        titulo: document.getElementById('edit-titulo').value,
        objetivo: document.getElementById('edit-descricao').value,
        descricao: document.getElementById('edit-descricao').value,
        estado: document.getElementById('edit-estado').value,
        area: document.getElementById('edit-area').value,
        apoio: document.getElementById('edit-apoio').value,
        tipo: document.getElementById('edit-tipo').value,
        data_final_submissao: document.getElementById('edit-data').value,
        valor_total: document.getElementById('edit-valor').value,
        tags: document.getElementById('edit-tags').value.split(',').map(t => t.trim()).filter(t => t),
        attachments: [
            { name: "Documento Principal", url: document.getElementById('edit-pdf').value }
        ]
    };

    try {
        let url = "http://127.0.0.1:8000/admin/editais";
        let method = "POST";
        if (isUpdate) {
            url = `http://127.0.0.1:8000/admin/editais/${id}`;
            method = "PUT";
        }

        const res = await fetch(url, {
            method: method,
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify(dados)
        });

        if (!res.ok) throw new Error("Erro ao salvar");

        alert(isUpdate ? "Edital atualizado!" : "Edital criado!");
        closeModal();
        carregarEditais(); 

    } catch (err) {
        alert("Erro: " + err.message);
    }
});

carregarEditais();
