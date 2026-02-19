/**
 * Path Display Utilities (T7d)
 * 將 file:/// URI 轉換為人類可讀的顯示路徑
 *
 * 規則：
 * - Windows 路徑（drive letter）：去除前綴，/ → \
 * - UNC 路徑（//server/share）：去除前綴，/ → \
 * - Linux/其他路徑：去除前綴，保留 /
 */
window.pathToDisplay = function(fileUri) {
    if (!fileUri) return '';
    const stripped = fileUri.replace(/^file:\/\/\//, '');
    if (/^[A-Za-z]:/.test(stripped)) return stripped.replace(/\//g, '\\');
    if (stripped.startsWith('//')) return stripped.replace(/\//g, '\\');
    return stripped;
};
