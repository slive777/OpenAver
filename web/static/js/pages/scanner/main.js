import { stateScan }  from '@/scanner/state-scan.js';
import { stateBatch } from '@/scanner/state-batch.js';
import { stateAlias } from '@/scanner/state-alias.js';
import { stateTagAlias } from '@/scanner/state-tag-alias.js';
import { browseDirState } from '@/shared/state-browse-dir.js';
import { toastState } from '@/shared/state-toast.js';
import { mergeState } from '@/shared/merge-state.js';
import { mediaProbeReminder } from '@/scanner/media-probe-reminder.js';

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
        browseDirState(),
        toastState(),
    ));
    // 198a-T5: 影片資訊讀取提醒（獨立元件，不進 mergeState）
    Alpine.data('mediaProbeReminder', mediaProbeReminder);
});
