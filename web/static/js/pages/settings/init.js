// 事件綁定
document.getElementById('translateEnabled').addEventListener('change', updateTranslateOptions);
document.getElementById('translateProvider').addEventListener('change', onTranslateProviderChange);
document.getElementById('testOllamaBtn').addEventListener('click', testOllamaConnection);
document.getElementById('testModelBtn').addEventListener('click', testModel);
document.getElementById('testGeminiBtn').addEventListener('click', testGeminiConnection);
document.getElementById('testGeminiTranslateBtn').addEventListener('click', testGeminiTranslation);

document.getElementById('settingsForm').addEventListener('submit', (e) => {
    e.preventDefault();
    saveConfig();
});

document.getElementById('resetBtn').addEventListener('click', async () => {
    if (confirm('確定要重置所有設定嗎？此操作將刪除所有自訂設定。')) {
        try {
            const resp = await fetch('/api/config', { method: 'DELETE' });
            const result = await resp.json();
            if (result.success) {
                await loadConfig();
                showToast('已恢復預設設定', 'success');
            } else {
                showToast('重置失敗: ' + result.error, 'error');
            }
        } catch (e) {
            showToast('重置失敗: ' + e.message, 'error');
        }
    }
});

// 重看新手引導
document.getElementById('btnRestartTutorial')?.addEventListener('click', () => {
    window.location.href = '/search?tutorial=restart';
});

// 載入版本資訊
async function loadVersion() {
    try {
        const resp = await fetch('/api/version');
        const data = await resp.json();
        if (data.success) {
            document.getElementById('appVersion').textContent = `v${data.version}`;
            // Version text styling is handled by .version-text class
        }
    } catch (e) {
        document.getElementById('appVersion').textContent = '無法載入';
    }
}

// 檢查更新
document.getElementById('btnCheckUpdate')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnCheckUpdate');
    const status = document.getElementById('updateStatus');

    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> 檢查中...';
    status.textContent = '';
    status.className = 'small';

    try {
        const resp = await fetch('/api/check-update');
        const data = await resp.json();

        if (data.success) {
            if (data.has_update) {
                status.innerHTML = `<a href="${data.download_url}" target="_blank" class="text-success">
                    <i class="bi bi-download"></i> 新版本 ${data.latest_version} 可用
                </a>`;
            } else {
                status.innerHTML = '<span style="color: var(--text-muted);"><i class="bi bi-check-circle"></i> 已是最新版本</span>';
            }
        } else {
            status.innerHTML = `<span class="text-error"><i class="bi bi-exclamation-circle"></i> ${data.error || '檢查失敗'}</span>`;
        }
    } catch (e) {
        status.innerHTML = '<span class="text-error"><i class="bi bi-exclamation-circle"></i> 網路錯誤</span>';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-cloud-download"></i> 檢查更新';
    }
});

// 初始載入
loadConfig();
loadVersion();
