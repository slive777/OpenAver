/**
 * ScannerCore - 核心模組
 * 狀態管理、工具函數、SSE EventSource、統計
 */

let directories = [];
let config = {};
let configDirty = false;
let isGenerating = false;  // 追蹤是否正在生成

// localStorage keys
const STORAGE_KEYS = {
    logs: 'avlist_logs',
    isGenerating: 'avlist_generating',
    lastStatus: 'avlist_last_status'
};

// 儲存 logs 到 localStorage
function saveLogs() {
    const logOutput = document.getElementById('logOutput');
    localStorage.setItem(STORAGE_KEYS.logs, logOutput.innerHTML);
}

// 從 localStorage 恢復 logs
function restoreLogs() {
    const savedLogs = localStorage.getItem(STORAGE_KEYS.logs);
    const wasGenerating = localStorage.getItem(STORAGE_KEYS.isGenerating) === 'true';

    if (savedLogs) {
        const logOutput = document.getElementById('logOutput');
        const progressSection = document.getElementById('progressSection');

        logOutput.innerHTML = savedLogs;
        progressSection.style.display = 'block';

        // 如果之前正在生成但被中斷
        if (wasGenerating) {
            logOutput.innerHTML += '<div class="log-warn">⚠ 生成被中斷（離開頁面）</div>';
            localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
        }

        // 恢復狀態文字
        const lastStatus = localStorage.getItem(STORAGE_KEYS.lastStatus);
        if (lastStatus) {
            document.getElementById('progressStatus').textContent = lastStatus;
        }
    }
}

// 清除 logs
function clearLogs() {
    localStorage.removeItem(STORAGE_KEYS.logs);
    localStorage.removeItem(STORAGE_KEYS.isGenerating);
    localStorage.removeItem(STORAGE_KEYS.lastStatus);
}

// === Log 批次處理 ===
let logBatch = [];
let logTimer = null;
const LOG_BATCH_INTERVAL = 100;  // 100ms 批次間隔

// 加入 log 到批次佇列
function addLog(cls, message) {
    const logOutput = document.getElementById('logOutput');
    logBatch.push(`<div class="${cls}">${escapeHtml(message)}</div>`);

    if (!logTimer) {
        logTimer = setTimeout(flushLogs, LOG_BATCH_INTERVAL);
    }
}

// 批次渲染 logs
function flushLogs() {
    if (logBatch.length === 0) {
        logTimer = null;
        return;
    }

    const logOutput = document.getElementById('logOutput');

    // 1. 批次插入 DOM（用 insertAdjacentHTML 避免重新解析整個 innerHTML）
    logOutput.insertAdjacentHTML('beforeend', logBatch.join(''));

    // 2. 滾動到底部
    logOutput.scrollTop = logOutput.scrollHeight;

    // 3. 只在批次結束時存一次 localStorage
    saveLogs();

    // 4. 清空批次
    logBatch = [];
    logTimer = null;
}

// 載入設定
async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const result = await resp.json();
        if (result.success) {
            config = result.data;
            directories = config.gallery?.directories || [];
            // Update output path display
            const outputDir = config.gallery?.output_dir || 'output';
            const outputFilename = config.gallery?.output_filename || 'gallery_output.html';
            document.getElementById('outputPathDisplay').textContent = `${outputDir}/${outputFilename}`;
            renderDirectories();
        }
    } catch (e) {
        console.error('載入設定失敗:', e);
    }
}

// 儲存設定
async function saveConfig() {
    try {
        config.gallery = config.gallery || {};
        config.gallery.directories = directories;
        // Keep existing output settings from config

        const resp = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const result = await resp.json();
        if (result.success) {
            configDirty = false;
            showToast('設定已儲存');
        } else {
            showToast('儲存失敗: ' + (result.error || '未知錯誤'));
        }
    } catch (e) {
        console.error('儲存失敗:', e);
        showToast('儲存失敗: ' + e.message);
    }
}

// 產生網頁
async function generate() {
    if (directories.length === 0) {
        showToast('請先加入至少一個資料夾');
        return;
    }

    // 自動儲存設定
    if (configDirty) {
        await saveConfig();
    }

    const btn = document.getElementById('btnGenerate');
    const progressSection = document.getElementById('progressSection');
    const logOutput = document.getElementById('logOutput');
    const doneActions = document.getElementById('doneActions');

    btn.disabled = true;
    btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span> 產生中...';
    progressSection.style.display = 'block';
    doneActions.style.display = 'none';
    logOutput.innerHTML = '';

    // 設置生成狀態
    isGenerating = true;
    localStorage.setItem(STORAGE_KEYS.isGenerating, 'true');
    clearLogs();  // 清除舊 logs

    try {
        const eventSource = new EventSource('/api/gallery/generate');

        eventSource.onmessage = function (event) {
            const data = JSON.parse(event.data);

            if (data.type === 'progress') {
                document.getElementById('progressStatus').textContent = data.status;
                const pct = data.total > 0 ? (data.current / data.total) * 100 : 0;
                document.getElementById('progressBar').style.width = `${pct}%`;
                // 儲存狀態
                localStorage.setItem(STORAGE_KEYS.lastStatus, data.status);
            } else if (data.type === 'log') {
                const cls = data.level === 'error' ? 'log-error' :
                    data.level === 'warn' ? 'log-warn' : 'log-info';
                addLog(cls, data.message);  // 使用批次處理
            } else if (data.type === 'done') {
                eventSource.close();
                isGenerating = false;
                localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
                // 清除 viewer 狀態，下次開啟會重新載入
                localStorage.removeItem('avlist_state');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-play-fill"></i> 產生網頁';
                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressStatus').textContent = `完成！${data.video_count} 部影片`;
                localStorage.setItem(STORAGE_KEYS.lastStatus, '完成');

                // Show done actions with copy path
                const doneActions = document.getElementById('doneActions');
                const btnCopyPath = document.getElementById('btnCopyPath');
                doneActions.style.display = 'flex';
                btnCopyPath.dataset.path = data.output_path;

                // 處理本次新增影片的 NFO 補全提示
                if (data.session_update && data.session_update.count > 0) {
                    document.getElementById('updateCount').textContent = data.session_update.count;
                    document.getElementById('statNeedUpdate').style.display = '';
                    // 儲存 paths 供修復按鈕使用
                    window.sessionUpdatePaths = data.session_update.paths;
                } else {
                    document.getElementById('statNeedUpdate').style.display = 'none';
                    window.sessionUpdatePaths = [];
                }

                // Show toast
                showToast(`成功產生 ${data.video_count} 部影片列表`);

                // 確保最後一批 log 顯示並儲存
                flushLogs();

                // 刷新統計資訊 (不含 NFO 檢查)
                loadStats();
            } else if (data.type === 'error') {
                eventSource.close();
                isGenerating = false;
                localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-play-fill"></i> 產生網頁';
                addLog('log-error', '錯誤: ' + data.message);
                flushLogs();
            }
        };

        eventSource.onerror = function () {
            eventSource.close();
            isGenerating = false;
            localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-play-fill"></i> 產生網頁';
            addLog('log-error', '連線中斷');
            flushLogs();
        };
    } catch (e) {
        isGenerating = false;
        localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-fill"></i> 產生網頁';
        alert('發生錯誤: ' + e.message);
    }
}

// Toast 提示
function showToast(msg) {
    const toast = document.getElementById('toastMsg');
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2500);
}

// 複製輸出路徑到剪貼簿
function copyOutputPath() {
    const btn = document.getElementById('btnCopyPath');
    const path = btn.dataset.path;
    if (path) {
        navigator.clipboard.writeText(path).then(() => {
            showToast('已複製: ' + path);
        }).catch(() => {
            alert('複製失敗，路徑：' + path);
        });
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// 載入統計資訊
async function loadStats() {
    try {
        const resp = await fetch('/api/gallery/stats');
        const result = await resp.json();
        if (result.success && result.data) {
            const stats = result.data;
            const statsCard = document.getElementById('statsCard');
            const statTotal = document.getElementById('statTotal');
            const statLastRun = document.getElementById('statLastRun');

            if (stats.total > 0) {
                statsCard.style.display = 'block';
                statTotal.textContent = stats.total;

                if (stats.last_run) {
                    const lastRun = new Date(stats.last_run);
                    const timeStr = lastRun.toLocaleString('zh-TW', {
                        month: 'numeric',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                    let runInfo = `上次執行: ${timeStr}`;
                    if (stats.last_added !== null && stats.last_added !== undefined) {
                        runInfo += ` (新增 ${stats.last_added} 部)`;
                    }
                    statLastRun.textContent = runInfo;
                }

                // 注意：不再自動呼叫 checkNeedUpdate()
                // NFO 更新提示僅在掃描後顯示本次新增的問題影片
            }
        }
    } catch (e) {
        console.error('載入統計失敗:', e);
    }
}

// 檢查需要更新的影片數量
async function checkNeedUpdate() {
    try {
        const resp = await fetch('/api/gallery/update-check');
        const result = await resp.json();
        if (result.success && result.data && result.data.need_update > 0) {
            document.getElementById('updateCount').textContent = result.data.need_update;
            document.getElementById('statNeedUpdate').style.display = '';
        } else {
            document.getElementById('statNeedUpdate').style.display = 'none';
        }
    } catch (e) {
        console.error('檢查更新失敗:', e);
    }
}

// 執行 NFO 更新
async function runNfoUpdate() {
    const btn = document.getElementById('btnUpdate');
    const progressSection = document.getElementById('progressSection');
    const logOutput = document.getElementById('logOutput');

    btn.disabled = true;
    btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span> 補全中...';
    progressSection.style.display = 'block';
    logOutput.innerHTML = '';

    // 設置生成狀態
    isGenerating = true;
    localStorage.setItem(STORAGE_KEYS.isGenerating, 'true');
    clearLogs();

    try {
        const eventSource = new EventSource('/api/gallery/update');

        eventSource.onmessage = function (event) {
            const data = JSON.parse(event.data);

            if (data.type === 'progress') {
                document.getElementById('progressStatus').textContent = data.status;
                const countEl = document.getElementById('progressCount');
                if (countEl) countEl.textContent = `${data.current} / ${data.total}`;
                const pct = data.total > 0 ? (data.current / data.total) * 100 : 0;
                document.getElementById('progressBar').style.width = `${pct}%`;
                localStorage.setItem(STORAGE_KEYS.lastStatus, data.status);
            } else if (data.type === 'log') {
                const cls = data.level === 'error' ? 'log-error' :
                    data.level === 'warn' ? 'log-warn' : 'log-info';
                addLog(cls, data.message);  // 使用批次處理
            } else if (data.type === 'done') {
                eventSource.close();
                isGenerating = false;
                localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
                // Keep button disabled and show completed state
                btn.disabled = true;
                btn.innerHTML = '<i class="bi bi-check-lg"></i> 已完成';
                btn.classList.add('completed');
                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressStatus').textContent = data.message || '完成';
                localStorage.setItem(STORAGE_KEYS.lastStatus, data.message || '完成');

                // 提示重新產生列表
                showToast('補全完成！請重新產生列表以更新');
                if (data.message) {
                    addLog('log-info', data.message);
                }
                flushLogs();
            } else if (data.type === 'error') {
                eventSource.close();
                isGenerating = false;
                localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
                addLog('log-error', '錯誤: ' + data.message);
                flushLogs();
            }
        };

        eventSource.onerror = function () {
            eventSource.close();
            isGenerating = false;
            localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
            addLog('log-error', '連線中斷');
            flushLogs();
        };
    } catch (e) {
        isGenerating = false;
        localStorage.setItem(STORAGE_KEYS.isGenerating, 'false');
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
        alert('發生錯誤: ' + e.message);
    }
}
