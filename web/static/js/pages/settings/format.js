// 格式變數清單
const formatVariables = [
    { name: '{num}', description: '番號', example: 'SONE-205' },
    { name: '{title}', description: '標題', example: '新人出道...' },
    { name: '{actor}', description: '演員（第一位）', example: '三上悠亜' },
    { name: '{actors}', description: '所有演員', example: '三上悠亜, 明日花' },
    { name: '{maker}', description: '片商', example: 'S1' },
    { name: '{date}', description: '發行日期', example: '2024-01-15' },
    { name: '{year}', description: '年份', example: '2024' }
];

// 初始化格式變數下拉選單
document.querySelectorAll('.variable-menu[data-type="format"]').forEach(menu => {
    formatVariables.forEach(v => {
        const div = document.createElement('div');
        div.className = 'variable-item';
        div.dataset.var = v.name;
        div.innerHTML = `
            <code class="variable-name">${v.name}</code>
            <span class="variable-desc">${v.description}</span>
            <small class="variable-example">例：${v.example}</small>
        `;
        menu.appendChild(div);
    });

    menu.addEventListener('click', (e) => {
        e.preventDefault();
        const item = e.target.closest('[data-var]');
        if (item) {
            const targetId = menu.dataset.target;
            const input = document.getElementById(targetId);
            const cursorPos = input.selectionStart;
            const textBefore = input.value.substring(0, cursorPos);
            const textAfter = input.value.substring(cursorPos);
            input.value = textBefore + item.dataset.var + textAfter;
            input.focus();
            input.setSelectionRange(cursorPos + item.dataset.var.length, cursorPos + item.dataset.var.length);
            // 更新預覽（如果是 folderFormat）
            if (targetId === 'folderFormat') updateFolderPreview();
        }
    });
});

// === 資料夾多層結構功能 ===
const FOLDER_PREVIEW_DATA = {
    num: 'SSNI-618',
    maker: 'SOD',
    actor: '三上悠亞',
    actors: '三上悠亞, 明日花',
    title: '絕對領域',
    date: '2024-01-15',
    year: '2024'
};

// 連動啟用邏輯（右→左：內 → 中 → 外）
function updateFolderLayers() {
    const createFolder = document.getElementById('createFolder').checked;
    const layer3Input = document.getElementById('folderLayer3');  // 內層
    const layer2Input = document.getElementById('folderLayer2');  // 中層
    const layer1Input = document.getElementById('folderLayer1');  // 外層

    const layer3Btn = document.getElementById('folderLayer3Btn');
    const layer2Btn = document.getElementById('folderLayer2Btn');
    const layer1Btn = document.getElementById('folderLayer1Btn');

    // 如果「建立資料夾」未勾選，全部 disabled
    if (!createFolder) {
        layer3Input.disabled = true;
        layer3Btn.disabled = true;
        layer2Input.disabled = true;
        layer2Btn.disabled = true;
        layer1Input.disabled = true;
        layer1Btn.disabled = true;
        updateFolderPreview();
        return;
    }

    // 「建立資料夾」已勾選，啟用內層
    layer3Input.disabled = false;
    layer3Btn.disabled = false;

    // 連動啟用
    const layer3HasValue = !!layer3Input.value.trim();
    const layer2HasValue = !!layer2Input.value.trim();

    layer2Input.disabled = !layer3HasValue;
    layer2Btn.disabled = !layer3HasValue;

    layer1Input.disabled = !layer2HasValue;
    layer1Btn.disabled = !layer2HasValue;

    // 禁用時清空
    if (layer2Input.disabled) layer2Input.value = '';
    if (layer1Input.disabled) layer1Input.value = '';

    updateFolderPreview();
}

function updateFolderPreview() {
    const createFolder = document.getElementById('createFolder').checked;

    // 格式化檔名預覽
    const filenameFormat = document.getElementById('filenameFormat').value || '{num} {title}';
    let filenamePreview = filenameFormat;
    for (const [key, val] of Object.entries(FOLDER_PREVIEW_DATA)) {
        filenamePreview = filenamePreview.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
    }

    // 如果「建立資料夾」未勾選，只顯示檔名
    if (!createFolder) {
        document.getElementById('folderPreview').textContent = filenamePreview + '.mp4';
        return;
    }

    // 收集所有層（由外到內）
    const layers = [
        document.getElementById('folderLayer1').value.trim(),
        document.getElementById('folderLayer2').value.trim(),
        document.getElementById('folderLayer3').value.trim()
    ].filter(v => v);

    // 格式化資料夾預覽
    let folderPreview = layers.map(layer => {
        let part = layer;
        for (const [key, val] of Object.entries(FOLDER_PREVIEW_DATA)) {
            part = part.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
        }
        return part;
    }).join('/');

    const folder = folderPreview ? folderPreview + '/' : '';
    document.getElementById('folderPreview').textContent = folder + filenamePreview + '.mp4';
}

// 初始化資料夾層變數下拉選單
document.querySelectorAll('.variable-menu[data-target^="folderLayer"]').forEach(menu => {
    menu.innerHTML = `
        <div class="variable-item" data-var="{num}"><code class="variable-name">{num}</code></div>
        <div class="variable-item" data-var="{actor}"><code class="variable-name">{actor}</code></div>
        <div class="variable-item" data-var="{maker}"><code class="variable-name">{maker}</code></div>
        <div class="variable-item" data-var="{title}"><code class="variable-name">{title}</code></div>
        <div class="variable-item" data-var="{year}"><code class="variable-name">{year}</code></div>
    `;
    menu.addEventListener('click', (e) => {
        const item = e.target.closest('[data-var]');
        if (item) {
            e.preventDefault();
            const targetId = menu.dataset.target;
            const input = document.getElementById(targetId);
            input.value += item.dataset.var;
            input.focus();
            updateFolderLayers();
        }
    });
});
