/**
 * ScannerAlias - 女優別名管理模組
 * 別名 CRUD、預覽、列表渲染
 */

// === 女優名稱管理 ===
let aliasCardCollapsed = true;
let previewDebounceTimer = null;

// 切換卡片展開/收起
function toggleAliasCard() {
    aliasCardCollapsed = !aliasCardCollapsed;
    const body = document.getElementById('aliasCardBody');
    const icon = document.getElementById('aliasCollapseIcon');

    if (aliasCardCollapsed) {
        body.style.display = 'none';
        icon.className = 'bi bi-chevron-down';
    } else {
        body.style.display = 'block';
        icon.className = 'bi bi-chevron-up';
        loadActressAliases();
    }
}

// 載入別名列表
async function loadActressAliases() {
    try {
        const resp = await fetch('/api/gallery/actress-aliases');
        const result = await resp.json();

        if (result.success) {
            renderAliasList(result.data);
        } else {
            document.getElementById('aliasList').innerHTML =
                `<div class="alias-list-error">載入失敗: ${result.error}</div>`;
        }
    } catch (e) {
        document.getElementById('aliasList').innerHTML =
            `<div class="alias-list-error">載入失敗: ${e.message}</div>`;
    }
}

// 渲染別名列表
function renderAliasList(aliases) {
    const list = document.getElementById('aliasList');

    if (!aliases || aliases.length === 0) {
        list.innerHTML = '<div class="alias-list-empty">尚無別名對照</div>';
        return;
    }

    list.innerHTML = aliases.map(alias => `
            <div class="alias-item" data-id="${alias.id}">
                <span class="alias-old">${escapeHtml(alias.old_name)}</span>
                <span class="alias-arrow"><i class="bi bi-arrow-right"></i></span>
                <span class="alias-new">${escapeHtml(alias.new_name)}</span>
                <span class="alias-applied">${alias.applied_count > 0 ? `(已套用 ${alias.applied_count})` : ''}</span>
                <button class="btn-alias-delete" onclick="deleteActressAlias(${alias.id})" title="刪除">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>
        `).join('');
}

// 預覽片數
async function previewAliasCount() {
    // 防抖
    if (previewDebounceTimer) {
        clearTimeout(previewDebounceTimer);
    }

    previewDebounceTimer = setTimeout(async () => {
        const oldName = document.getElementById('aliasOldName').value.trim();
        const newName = document.getElementById('aliasNewName').value.trim();
        const preview = document.getElementById('aliasPreview');
        const oldCount = document.getElementById('oldNameCount');
        const newCount = document.getElementById('newNameCount');

        // 清除顯示
        oldCount.textContent = '';
        newCount.textContent = '';
        preview.textContent = '';

        if (oldName) {
            try {
                const resp = await fetch(`/api/gallery/actress-stats?name=${encodeURIComponent(oldName)}`);
                const result = await resp.json();
                if (result.success) {
                    oldCount.textContent = `${result.data.count} 部`;
                }
            } catch (e) { }
        }

        if (newName) {
            try {
                const resp = await fetch(`/api/gallery/actress-stats?name=${encodeURIComponent(newName)}`);
                const result = await resp.json();
                if (result.success) {
                    newCount.textContent = `${result.data.count} 部`;
                }
            } catch (e) { }
        }

        // 顯示預覽
        if (oldName && newName) {
            const oldC = parseInt(oldCount.textContent) || 0;
            const newC = parseInt(newCount.textContent) || 0;
            if (oldC > 0) {
                preview.innerHTML = `<i class="bi bi-info-circle"></i> 將有 ${oldC} 部影片的 "${escapeHtml(oldName)}" 改為 "${escapeHtml(newName)}"`;
            }
        }
    }, 300);
}

// 新增別名
async function addActressAlias() {
    const oldName = document.getElementById('aliasOldName').value.trim();
    const newName = document.getElementById('aliasNewName').value.trim();

    if (!oldName || !newName) {
        showToast('請輸入舊名稱和新名稱');
        return;
    }

    if (oldName === newName) {
        showToast('新舊名稱不可相同');
        return;
    }

    const btn = document.getElementById('btnAddAlias');
    btn.disabled = true;

    try {
        const resp = await fetch('/api/gallery/actress-aliases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_name: oldName, new_name: newName })
        });
        const result = await resp.json();

        if (result.success) {
            showToast('已新增別名對照');
            document.getElementById('aliasOldName').value = '';
            document.getElementById('aliasNewName').value = '';
            document.getElementById('oldNameCount').textContent = '';
            document.getElementById('newNameCount').textContent = '';
            document.getElementById('aliasPreview').textContent = '';
            loadActressAliases();
        } else {
            showToast('新增失敗: ' + result.error);
        }
    } catch (e) {
        showToast('新增失敗: ' + e.message);
    } finally {
        btn.disabled = false;
    }
}

// 刪除別名
async function deleteActressAlias(id) {
    if (!confirm('確定要刪除這個別名對照嗎？')) {
        return;
    }

    try {
        const resp = await fetch(`/api/gallery/actress-aliases/${id}`, {
            method: 'DELETE'
        });
        const result = await resp.json();

        if (result.success) {
            showToast('已刪除');
            loadActressAliases();
        } else {
            showToast('刪除失敗: ' + result.error);
        }
    } catch (e) {
        showToast('刪除失敗: ' + e.message);
    }
}
