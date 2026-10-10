import { stateConfig }       from '@/settings/state-config.js';
import { stateProviders }    from '@/settings/state-providers.js';
import { stateUI }           from '@/settings/state-ui.js';
import { stateSourceProbe }  from '@/settings/state-source-probe.js';
import { customSources }     from '@/settings/state-custom-sources.js';
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
});
