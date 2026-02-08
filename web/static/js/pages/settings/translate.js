// ===== Gemini API Key 測試 =====
async function testGeminiConnection() {
    const apiKey = document.getElementById('geminiApiKey').value;
    const statusEl = document.getElementById('geminiStatus');
    const testBtn = document.getElementById('testGeminiBtn');
    const modelSelect = document.getElementById('geminiModel');
    const hintEl = document.getElementById('geminiModelStatus');

    if (!apiKey) {
        statusEl.innerHTML = '<span class="text-error"><i class="bi bi-x-circle"></i> 請輸入 API Key</span>';
        return;
    }

    // 禁用按鈕，顯示加載狀態
    testBtn.disabled = true;
    testBtn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
    statusEl.innerHTML = '<span style="color: var(--text-muted);">連線中...</span>';

    try {
        const response = await fetch('/api/gemini/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });

        const data = await response.json();

        if (data.success) {
            // 成功：顯示找到的模型數量
            statusEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle"></i> 找到 ${data.count} 個 Flash 模型</span>`;

            // 填充模型下拉框
            populateGeminiModels(data.models);

            // 啟用模型下拉框和測試按鈕
            modelSelect.disabled = false;
            document.getElementById('testGeminiTranslateBtn').disabled = false;

        } else {
            // 失敗：顯示錯誤信息
            statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> ${data.error || '連接失敗'}</span>`;

            // 禁用模型下拉框
            modelSelect.disabled = true;
            modelSelect.innerHTML = '<option value="">-- 請先測試 API Key --</option>';
            if (hintEl) hintEl.textContent = '';
        }

    } catch (error) {
        statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> ${error.message}</span>`;
    } finally {
        // 恢復按鈕
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="bi bi-plug"></i> 測試';
    }
}

// 填充 Gemini 模型下拉框
function populateGeminiModels(models) {
    const select = document.getElementById('geminiModel');
    const savedModel = select.value;

    select.innerHTML = '';

    models.forEach((model, index) => {
        const option = document.createElement('option');
        option.value = model.name;

        // 添加推薦標籤
        if (index === 0 && model.name.includes('lite')) {
            option.textContent = `${model.name} (推薦，最快)`;
        } else if (index === 0) {
            option.textContent = `${model.name} (推薦)`;
        } else {
            option.textContent = model.name;
        }

        select.appendChild(option);
    });

    // 恢復之前選擇的模型
    if (savedModel && models.some(m => m.name === savedModel)) {
        select.value = savedModel;
    }
}

// 測試 Gemini 翻譯功能
async function testGeminiTranslation() {
    const apiKey = document.getElementById('geminiApiKey').value;
    const model = document.getElementById('geminiModel').value;
    const statusEl = document.getElementById('geminiModelStatus');
    const testBtn = document.getElementById('testGeminiTranslateBtn');

    if (!apiKey) {
        statusEl.innerHTML = '<span class="text-error"><i class="bi bi-x-circle"></i> 請先輸入 API Key</span>';
        return;
    }

    if (!model) {
        statusEl.innerHTML = '<span class="text-error"><i class="bi bi-x-circle"></i> 請先選擇模型</span>';
        return;
    }

    // 禁用按鈕，顯示加載狀態
    testBtn.disabled = true;
    testBtn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
    statusEl.innerHTML = '<span style="color: var(--text-muted);">測試翻譯中...</span>';

    try {
        const response = await fetch('/api/gemini/test-translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: apiKey,
                model: model
            })
        });

        const data = await response.json();

        if (data.success) {
            // 翻譯成功
            statusEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> 翻譯測試成功！ (${data.translation})</span>`;
        } else {
            // 翻譯失敗 - 顯示 Google 的錯誤訊息
            statusEl.innerHTML = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${data.error}</span>`;
        }

    } catch (error) {
        statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> 測試失敗: ${error.message}</span>`;
    } finally {
        // 恢復按鈕
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="bi bi-chat-dots"></i> 測試';
    }
}

// 載入 Ollama 模型列表（靜默版本，頁面載入時使用）
async function loadOllamaModels(url, savedModel = '') {
    const statusEl = document.getElementById('ollamaStatus');
    const modelSelect = document.getElementById('ollamaModel');

    if (!url) return;

    statusEl.innerHTML = '<span style="color: var(--text-muted);">載入模型中...</span>';

    try {
        const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
        const result = await resp.json();

        if (result.success && result.models && result.models.length > 0) {
            modelSelect.innerHTML = result.models.map(m =>
                `<option value="${m}">${m}</option>`
            ).join('');

            // 設定儲存的模型
            if (savedModel && result.models.includes(savedModel)) {
                modelSelect.value = savedModel;
            }

            statusEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle"></i> ${result.models.length} 個模型</span>`;
        } else {
            statusEl.innerHTML = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${result.error || '無法連線'}</span>`;
        }
    } catch (e) {
        statusEl.innerHTML = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> 無法連線</span>`;
    }
}

// 測試 Ollama 連線並載入模型
async function testOllamaConnection() {
    const url = document.getElementById('ollamaUrl').value.trim();
    const statusEl = document.getElementById('ollamaStatus');
    const modelSelect = document.getElementById('ollamaModel');
    const btn = document.getElementById('testOllamaBtn');

    if (!url) {
        statusEl.innerHTML = '<span class="text-error">請輸入 URL</span>';
        return;
    }

    // 顯示載入中
    btn.disabled = true;
    btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
    statusEl.innerHTML = '<span style="color: var(--text-muted);">連線中...</span>';

    try {
        const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
        const result = await resp.json();

        if (result.success && result.models && result.models.length > 0) {
            // 成功：填入模型選單
            const currentModel = modelSelect.value;
            modelSelect.innerHTML = result.models.map(m =>
                `<option value="${m}">${m}</option>`
            ).join('');

            // 保留之前選擇的模型（如果還存在）
            if (currentModel && result.models.includes(currentModel)) {
                modelSelect.value = currentModel;
            }

            statusEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle"></i> 已連線，${result.models.length} 個模型</span>`;
        } else {
            statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error || '無可用模型'}</span>`;
            modelSelect.innerHTML = '<option value="">-- 連線失敗 --</option>';
        }
    } catch (e) {
        statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
        modelSelect.innerHTML = '<option value="">-- 連線失敗 --</option>';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-plug"></i> 測試';
    }
}

// 測試模型是否能正常回應
async function testModel() {
    const url = document.getElementById('ollamaUrl').value.trim();
    const model = document.getElementById('ollamaModel').value;
    const statusEl = document.getElementById('modelStatus');
    const btn = document.getElementById('testModelBtn');

    if (!url || !model) {
        statusEl.innerHTML = '<span class="text-error">請先選擇模型</span>';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
    statusEl.innerHTML = '<span style="color: var(--text-muted);">測試中...</span>';

    try {
        // 直接調用 Ollama API 測試當前選擇的模型
        const resp = await fetch('/api/ollama/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, model })
        });
        const result = await resp.json();

        if (result.success) {
            statusEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle"></i> ${result.result}</span>`;
        } else {
            statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error}</span>`;
        }
    } catch (e) {
        statusEl.innerHTML = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-chat-dots"></i> 測試';
    }
}
