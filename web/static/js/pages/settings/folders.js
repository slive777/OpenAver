// 選擇輸出資料夾 (PyWebView)
async function selectOutputFolder() {
    if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
        alert('此功能需要在桌面應用程式中使用');
        return;
    }

    try {
        const result = await window.pywebview.api.select_folder();
        if (result && result.folder) {
            document.getElementById('avlistOutputDir').value = result.folder;
        }
    } catch (e) {
        console.error('選擇資料夾失敗:', e);
    }
}
