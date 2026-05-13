import { stateScan }  from '@/scanner/state-scan.js';
import { stateBatch } from '@/scanner/state-batch.js';
import { stateAlias } from '@/scanner/state-alias.js';
import { stateTagAlias } from '@/scanner/state-tag-alias.js';

function mergeState(...parts) {
    const target = {};
    for (const part of parts) {
        Object.defineProperties(target, Object.getOwnPropertyDescriptors(part));
    }
    return target;
}

// PyWebView 拖曳橋接（從 scanner.js L1528–L1542 搬移）
window.handleFolderDrop = function (folderPaths) {
    if (!folderPaths || folderPaths.length === 0) {
        return;
    }

    if (typeof window.addScannerFolder !== 'function') {
        console.error('[AVList] Alpine not ready, addScannerFolder not available');
        return;
    }

    for (const folderPath of folderPaths) {
        window.addScannerFolder(folderPath);
    }
};

document.addEventListener('alpine:init', () => {
    Alpine.data('scanner', () => mergeState(
        stateScan(),
        stateBatch(),
        stateAlias(),
        stateTagAlias(),
    ));
});
