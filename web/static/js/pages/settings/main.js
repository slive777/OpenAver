import { stateConfig }       from '@/settings/state-config.js';
import { stateProviders }    from '@/settings/state-providers.js';
import { stateUI }           from '@/settings/state-ui.js';
import { stateSourceProbe }  from '@/settings/state-source-probe.js';
import { customSources }     from '@/settings/state-custom-sources.js';
import { aiServicesCard }    from '@/settings/ai-services-card.js';
import { aiSimilarPanel }    from '@/settings/ai-similar-panel.js';
import { aiFacesPanel }      from '@/settings/ai-faces-panel.js';
import { browseDirState }    from '@/shared/state-browse-dir.js';
import { toastState }        from '@/shared/state-toast.js';
import { mergeState }        from '@/shared/merge-state.js';

document.addEventListener('alpine:init', () => {
    Alpine.data('settings', () => mergeState(
        stateConfig(),
        stateProviders(),
        stateUI(),
        stateSourceProbe(),
        browseDirState(),
        toastState(),
    ));
    // 165-T9: 自訂來源是獨立元件（不進 mergeState）
    Alpine.data('customSources', customSources);
    // 186-T2: AI 功能卡分頁殼（不進 mergeState）
    Alpine.data('aiServicesCard', aiServicesCard);
    // 186-T6: 圖片相似分頁（不進 mergeState）
    Alpine.data('aiSimilarPanel', aiSimilarPanel);
    // 187a-T5: 人臉分頁（不進 mergeState）
    Alpine.data('aiFacesPanel', aiFacesPanel);
});
