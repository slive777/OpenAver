import {
    acceptProbeResponse,
    buildProbeKey,
    pickProbeIds,
    summarizeProbe,
} from '@/settings/source-probe-logic.js';

/**
 * 測試連線分片（163b-T4a，CD-8）。
 * 讀 host 的 form / sources / showToast；不定義 init()，不碰 $watch（watcher 掛在模板）。
 * 全站唯一呼叫測試連線端點的地方。
 */
export function stateSourceProbe() {
    return {
        srcProbeStatus: 'idle',   // 'idle' | 'running'
        srcProbeResults: {},      // 以來源 id 字串為鍵，整包重新賦值
        srcProbeGen: 0,
        srcProbeTipId: null,      // 消費端在 T4b

        get srcProbeKey() {
            return buildProbeKey(this.form.proxyUrl, this.form.proxyScope, this.sources);
        },

        get srcProbeSummary() {
            return summarizeProbe(this.srcProbeResults);
        },

        // 唯一遞增世代處；冪等、對 idle 狀態無其他副作用
        clearSrcProbe() {
            this.srcProbeGen++;
            this.srcProbeResults = {};
            this.srcProbeTipId = null;
            this.srcProbeStatus = 'idle';
        },

        async runSrcProbe() {
            this.clearSrcProbe();
            const gen = this.srcProbeGen;
            this.srcProbeStatus = 'running';
            const ids = pickProbeIds(this.sources);
            try {
                const res = await fetch('/api/sources/probe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        proxy_url: String(this.form.proxyUrl ?? '').trim(),
                        proxy_scope: this.form.proxyScope,
                        source_ids: ids,
                    }),
                });
                if (!res.ok) throw new Error('probe http ' + res.status);
                const data = await res.json();
                if (!acceptProbeResponse(gen, this.srcProbeGen)) return;
                if (!data || typeof data.results !== 'object' || data.results === null) {
                    throw new Error('probe response missing results');
                }
                this.srcProbeResults = data.results;
                this.srcProbeStatus = 'idle';
            } catch (e) {
                const stale = !acceptProbeResponse(gen, this.srcProbeGen);
                if (stale) return;
                this.srcProbeResults = {};
                this.srcProbeStatus = 'idle';
                this.showToast(window.t('settings.sources.probe_failed'), 'error');
            }
        },
    };
}
