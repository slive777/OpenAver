// 載入設定
async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const result = await resp.json();
        if (result.success) {
            const config = result.data;

            // Scraper 設定
            document.getElementById('createFolder').checked = config.scraper.create_folder;

            // 資料夾層（新格式 folder_layers 或對後兼容試圖分解舊的 folder_format）
            const layers = config.scraper.folder_layers || [];
            if (layers.length >= 1) {
                document.getElementById('folderLayer3').value = layers[layers.length - 1] || '';
            }
            if (layers.length >= 2) {
                document.getElementById('folderLayer2').value = layers[layers.length - 2] || '';
            }
            if (layers.length >= 3) {
                document.getElementById('folderLayer1').value = layers[layers.length - 3] || '';
            }
            // 如果沒有 folder_layers，嘗試從舊的 folder_format 讀取
            if (layers.length === 0 && config.scraper.folder_format) {
                document.getElementById('folderLayer3').value = config.scraper.folder_format;
            }

            // 先設定 filenameFormat，再更新預覽（預覽會用到 filenameFormat）
            document.getElementById('filenameFormat').value = config.scraper.filename_format;
            updateFolderLayers();
            document.getElementById('maxTitleLength').value = config.scraper.max_title_length;
            document.getElementById('maxFilenameLength').value = config.scraper.max_filename_length;
            document.getElementById('videoExtensions').value = config.scraper.video_extensions.join(', ');


            // 搜尋設定
            if (config.search) {
                document.getElementById('galleryModeEnabled').checked = config.search.gallery_mode_enabled || false;
                document.getElementById('uncensoredModeEnabled').checked = config.search.uncensored_mode_enabled || false;
                document.getElementById('searchFavoriteFolder').value = config.search.favorite_folder || '';
            }

            // 翻譯設定
            document.getElementById('translateEnabled').checked = config.translate.enabled;
            document.getElementById('translateProvider').value = config.translate.provider || 'ollama';
            // Ollama 設定（支持新的嵌套结构和旧的扁平结构）
            document.getElementById('ollamaUrl').value = config.translate.ollama?.url || config.translate.ollama_url || '';

            // Gemini 設定
            if (config.translate.gemini) {
                document.getElementById('geminiApiKey').value = config.translate.gemini.api_key || '';
                // 預設填入模型（稍後測試時會更新）
                const geminiModel = document.getElementById('geminiModel');
                if (config.translate.gemini.model) {
                    geminiModel.innerHTML = `<option value="${config.translate.gemini.model}">${config.translate.gemini.model}</option>`;
                    geminiModel.value = config.translate.gemini.model;
                }

                // 如果有 API Key，自動測試獲取模型列表
                if (config.translate.gemini.api_key && config.translate.provider === 'gemini') {
                    setTimeout(() => testGeminiConnection(), 100);
                }
            }

            updateTranslateOptions();

            // AVList 設定
            if (config.gallery) {
                document.getElementById('avlistMode').value = config.gallery.default_mode || 'image';
                document.getElementById('avlistSort').value = config.gallery.default_sort || 'date';
                document.getElementById('avlistOrder').value = config.gallery.default_order || 'descending';
                document.getElementById('avlistItemsPerPage').value = config.gallery.items_per_page || 90;
                document.getElementById('avlistMinSize').value = config.gallery.min_size_mb || 0;
                document.getElementById('avlistOutputDir').value = config.gallery.output_dir || 'output';
                document.getElementById('avlistOutputFilename').value = config.gallery.output_filename || 'gallery_output.html';
            }

            // 瀏覽器設定
            if (config.showcase) {
                document.getElementById('viewerPlayer').value = config.showcase.player || '';
            }

            // 一般設定
            if (config.general) {
                let defaultPage = config.general.default_page || 'search';
                // 向後兼容：舊配置 "gallery" 映射到新值 "scanner"
                if (defaultPage === 'gallery') defaultPage = 'scanner';
                document.getElementById('defaultPage').value = defaultPage;
                document.getElementById('themeMode').value = config.general.theme || 'light';
                document.getElementById('sidebarCollapsed').checked = config.general.sidebar_collapsed || false;
                // Alpine.js x-model 會自動同步主題
            }

            // 自動載入 Ollama 模型列表（如果有 URL 且是 Ollama provider）
            const ollamaUrl = config.translate.ollama?.url || config.translate.ollama_url;
            const ollamaModel = config.translate.ollama?.model || config.translate.ollama_model;
            if (ollamaUrl && config.translate.provider === 'ollama') {
                await loadOllamaModels(ollamaUrl, ollamaModel);
            }
        }
    } catch (e) {
        console.error('載入設定失敗:', e);
    }
}

// 儲存設定
async function saveConfig() {
    try {
        // 先載入現有設定，避免覆蓋其他頁面的資料
        const currentResp = await fetch('/api/config');
        const currentResult = await currentResp.json();
        if (!currentResult.success) {
            showToast('載入現有設定失敗', 'danger');
            return;
        }
        const config = currentResult.data;

        // 更新 scraper 設定
        const folderLayers = [
            document.getElementById('folderLayer1').value.trim(),
            document.getElementById('folderLayer2').value.trim(),
            document.getElementById('folderLayer3').value.trim()
        ].filter(v => v);

        config.scraper = {
            ...config.scraper,
            create_folder: document.getElementById('createFolder').checked,
            folder_layers: folderLayers,  // 新格式
            folder_format: folderLayers.join('/') || '{num}',  // 向後兼容
            filename_format: document.getElementById('filenameFormat').value,
            max_title_length: parseInt(document.getElementById('maxTitleLength').value),
            max_filename_length: parseInt(document.getElementById('maxFilenameLength').value),
            video_extensions: document.getElementById('videoExtensions').value
                .split(',').map(s => s.trim()).filter(s => s)
        };

        // 更新 search 設定
        config.search = {
            ...config.search,
            gallery_mode_enabled: document.getElementById('galleryModeEnabled').checked,
            uncensored_mode_enabled: document.getElementById('uncensoredModeEnabled').checked,
            favorite_folder: document.getElementById('searchFavoriteFolder').value.trim()
        };

        // 更新 translate 設定（使用新的嵌套结构）
        config.translate = {
            ...config.translate,
            enabled: document.getElementById('translateEnabled').checked,
            provider: document.getElementById('translateProvider').value,
            ollama: {
                url: document.getElementById('ollamaUrl').value,
                model: document.getElementById('ollamaModel').value
            },
            gemini: {
                api_key: document.getElementById('geminiApiKey').value,
                model: document.getElementById('geminiModel').value || 'gemini-flash-lite-latest'
            }
        };

        // 更新 avlist 設定
        config.gallery = {
            ...config.gallery,
            default_mode: document.getElementById('avlistMode').value,
            default_sort: document.getElementById('avlistSort').value,
            default_order: document.getElementById('avlistOrder').value,
            items_per_page: parseInt(document.getElementById('avlistItemsPerPage').value),
            min_size_mb: parseInt(document.getElementById('avlistMinSize').value) || 0,
            output_dir: document.getElementById('avlistOutputDir').value.trim() || 'output',
            output_filename: document.getElementById('avlistOutputFilename').value.trim() || 'gallery_output.html'
        };

        // 更新 viewer 設定
        config.showcase = {
            ...config.showcase,
            player: document.getElementById('viewerPlayer').value.trim()
        };

        // 更新 general 設定
        config.general = {
            ...config.general,
            default_page: document.getElementById('defaultPage').value,
            theme: document.getElementById('themeMode').value,
            sidebar_collapsed: document.getElementById('sidebarCollapsed').checked
        };

        const resp = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const result = await resp.json();
        if (result.success) {
            showToast('設定已儲存', 'success');
            // Alpine.js x-model 會自動同步主題到 localStorage
        } else {
            showToast('儲存失敗: ' + result.error, 'danger');
        }
    } catch (e) {
        showToast('儲存失敗: ' + e.message, 'danger');
    }
}

// 更新翻譯選項顯示
function updateTranslateOptions() {
    const enabled = document.getElementById('translateEnabled').checked;
    document.getElementById('translateOptions').style.opacity = enabled ? '1' : '0.5';
    document.querySelectorAll('#translateOptions input, #translateOptions select, #translateOptions button').forEach(el => {
        // 不禁用整個區塊，只處理 opacity
        if (!enabled) {
            el.disabled = true;
        }
    });

    if (enabled) {
        // 先啟用 Provider 下拉選單
        document.getElementById('translateProvider').disabled = false;
        // 再應用 Provider 切換邏輯
        onTranslateProviderChange();
    }
}

// ===== Provider 切換邏輯 =====
function onTranslateProviderChange() {
    const provider = document.getElementById('translateProvider').value;
    const ollamaFields = document.getElementById('ollamaFields');
    const geminiFields = document.getElementById('geminiFields');
    const enabled = document.getElementById('translateEnabled').checked;

    if (provider === 'ollama') {
        ollamaFields.style.display = 'block';
        geminiFields.style.display = 'none';
        // 啟用 Ollama 字段
        if (enabled) {
            ollamaFields.querySelectorAll('input, select, button').forEach(el => el.disabled = false);
        }
    } else if (provider === 'gemini') {
        ollamaFields.style.display = 'none';
        geminiFields.style.display = 'block';
        // 啟用 Gemini 字段（除了模型選擇，需要先測試 API Key）
        if (enabled) {
            geminiFields.querySelectorAll('input, button').forEach(el => el.disabled = false);
            // 模型選擇保持 disabled 直到測試成功
            const geminiModel = document.getElementById('geminiModel');
            if (geminiModel.options.length <= 1 || !geminiModel.options[0].value) {
                geminiModel.disabled = true;
            }
        }
    }
}

// Toast 提示
function showToast(message, type = 'info') {
    // 簡單的 alert，可以之後改成 Bootstrap toast
    if (type === 'success') {
        alert(message);
    } else {
        alert('錯誤: ' + message);
    }
}
