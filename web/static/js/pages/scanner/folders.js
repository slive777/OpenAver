/**
 * ScannerFolders - 資料夾管理模組
 * 資料夾列表、拖放、PyWebView 對接
 */

// 渲染資料夾列表
function renderDirectories() {
    const list = document.getElementById('directoryList');

    if (directories.length === 0) {
        list.innerHTML = `
            <div class="folder-empty">
                <i class="bi bi-folder-plus"></i>
                <p>尚未加入任何資料夾</p>
                <p>點擊上方按鈕或拖曳資料夾至此</p>
            </div>
        `;
        return;
    }

    list.innerHTML = directories.map((dir, idx) => `
        <div class="folder-item">
            <i class="bi bi-folder folder-icon"></i>
            <span class="folder-path">${escapeHtml(dir)}</span>
            <button class="btn btn-sm btn-outline btn-error btn-remove" onclick="removeDirectory(${idx})" title="移除">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `).join('');
}

// 選擇資料夾 (PyWebView)
async function selectFolder() {
    console.log('[AVList] selectFolder called');

    if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
        console.log('[AVList] PyWebView not available');
        toggleManualInput();
        alert('此功能需要在桌面應用程式中使用');
        return;
    }

    try {
        console.log('[AVList] Calling select_folder...');
        // select_folder() 返回格式: { folder: "路徑", files: [...] }
        const result = await window.pywebview.api.select_folder();
        console.log('[AVList] select_folder result:', result);

        // 新格式：result 是物件 { folder, files }
        if (result && result.folder) {
            addFolderPath(result.folder);
        }
        // 舊格式兼容：result 是陣列
        else if (Array.isArray(result) && result.length > 0) {
            const firstFile = result[0];
            const lastSep = Math.max(firstFile.lastIndexOf('\\'), firstFile.lastIndexOf('/'));
            const folderPath = lastSep > 0 ? firstFile.substring(0, lastSep) : null;
            if (folderPath) {
                addFolderPath(folderPath);
            }
        } else {
            console.log('[AVList] No folder selected');
        }
    } catch (e) {
        console.error('[AVList] 選取資料夾失敗:', e);
    }
}

// 加入資料夾路徑（避免重複）
function addFolderPath(folderPath) {
    console.log('[AVList] addFolderPath called with:', folderPath);
    if (!directories.includes(folderPath)) {
        directories.push(folderPath);
        configDirty = true;
        renderDirectories();
        console.log('[AVList] Folder added successfully');
    } else {
        console.log('[AVList] Folder already in list');
        alert('此資料夾已在列表中');
    }
}

// 切換手動輸入區
function toggleManualInput() {
    const el = document.getElementById('manualInput');
    el.style.display = el.style.display === 'none' ? 'flex' : 'none';
    if (el.style.display === 'flex') {
        document.getElementById('manualPath').focus();
    }
}

// 加入手動輸入的路徑
function addManualPath() {
    const input = document.getElementById('manualPath');
    const path = input.value.trim();
    if (!path) return;

    if (directories.includes(path)) {
        alert('此資料夾已在列表中');
        return;
    }

    directories.push(path);
    configDirty = true;
    renderDirectories();
    input.value = '';
}

// 移除資料夾
function removeDirectory(idx) {
    directories.splice(idx, 1);
    configDirty = true;
    renderDirectories();
}

// PyWebView 拖曳處理 - 接收資料夾路徑（由 standalone.py 呼叫）
window.handleFolderDrop = function (folderPaths) {
    console.log('[AVList] handleFolderDrop called with:', folderPaths);

    if (!folderPaths || folderPaths.length === 0) {
        console.log('[AVList] handleFolderDrop: empty or null folderPaths');
        return;
    }

    let added = 0;
    for (const folderPath of folderPaths) {
        console.log('[AVList] Processing folder:', folderPath);
        if (!directories.includes(folderPath)) {
            directories.push(folderPath);
            added++;
            console.log('[AVList] Added folder:', folderPath);
        } else {
            console.log('[AVList] Folder already exists:', folderPath);
        }
    }

    if (added > 0) {
        configDirty = true;
        renderDirectories();
        console.log('[AVList] Rendered', added, 'new folders');
    }
};
