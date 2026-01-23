export function renderEditais(container, editais) {
    container.innerHTML = '';

    if (!editais || editais.length === 0) {
        container.innerHTML =
            '<p class="no-results">Nenhum edital encontrado com os filtros aplicados.</p>';
        return;
    }

    editais.forEach((edital, index) => {
        const card = document.createElement('div');
        card.classList.add('notice-card');

        card.dataset.id = edital.id;
        card.style.setProperty('--animation-delay', `${index * 0.1}s`);

        // TAGS VISUAIS (Removidos Apoio e Tipo)
        const tagsHtml = `
            ${edital.area ? `<span class="tag tag-area">${edital.area}</span>` : ''}
            ${edital.estado ? `<span class="tag tag-estado">${edital.estado}</span>` : ''}
            ${
                edital.tags && edital.tags.length
                    ? edital.tags
                          .slice(0, 2) 
                          .map(
                              (tag) =>
                                  `<span class="tag tag-tema">${tag}</span>`
                          )
                          .join('')
                    : ''
            }
        `;

        // Botão de Compartilhar (usando stopPropagation para não abrir o modal)
        // A função alert() é usada para simplicidade, mas poderia ser um toast notification
        const shareButton = edital.share_link 
            ? `<button class="share-btn" title="Copiar Link" onclick="navigator.clipboard.writeText('${edital.share_link}'); alert('Link copiado!'); event.stopPropagation();">
                 <i class="fas fa-share-alt"></i>
               </button>` 
            : '';

        card.innerHTML = `
            <div class="card-header-actions">
                ${edital.icone ? `
                    <div class="notice-icon">
                        <img src="${edital.icone}" alt="${edital.instituicao}">
                    </div>
                ` : '<div></div>'}
                ${shareButton}
            </div>

            <h3>${edital.titulo}</h3>
            <p class="description">${edital.descricao}</p>

            <div class="details">
                ${edital.data_fechamento 
                    ? `<p><strong>Data limite:</strong> ${edital.data_fechamento}</p>` 
                    : '<p><strong>Data limite:</strong> Não informada</p>'}
            </div>

            <div class="tags">
                ${tagsHtml}
            </div>
        `;

        container.appendChild(card);
    });
}