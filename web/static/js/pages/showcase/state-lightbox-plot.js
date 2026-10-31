/**
 * state-lightbox-plot.js — Showcase ESM（187b-T5a）
 *
 * 燈箱簡介面：讀 NFO plot → 翻譯 → 寫回 NFO／DB（POST /api/showcase/video/plot）→ toast「復原」。
 * mergeState 分片（plan-187b CD-9）：不定義 init()（FE-ALPINE-05）、頂層 key 一律 lbPlot／_lbPlot 前綴。
 * 時序（CD-10）：讀取用 _lbPlotGen 世代；翻譯鎖 _lbPlotInFlight[path] 在任何 await 之前設起；
 * 結果只寫「按下當下捕獲的 view 物件」。禁止用物件身分（!==）比對 view（Alpine Proxy）。
 */

import { translateFailureToastKey } from '@/shared/translate-provider.js';
import { plotFaceButtons, sameAfterNormalize } from './lb-plot-logic.js';

const LB_PLOT_UNDO_TOAST_MS = 6000;

function emptyPlotView() {
    return {
        path: '',
        loading: false,
        error: false,
        plot: '',
        original: '',
        hasOriginal: false,
        showing: 'plot',
    };
}

export function stateLightboxPlot() {
    return {
        lbPlotOpen: false,
        _lbPlotView: emptyPlotView(),
        _lbPlotInFlight: {},
        _lbPlotGen: 0,

        get lbPlotTranslateEnabled() {
            return typeof window !== 'undefined' && window.__SHOWCASE_TRANSLATE__?.enabled === true;
        },

        get lbPlotButtons() {
            return plotFaceButtons({
                translateEnabled: this.lbPlotTranslateEnabled,
                hasOriginal: this._lbPlotView.hasOriginal,
                showing: this._lbPlotView.showing,
            });
        },

        lbPlotShowButton() {
            return this.currentLightboxVideo?.has_plot === true && !!this.currentLightboxVideo?.path;
        },

        lbPlotToggle() {
            if (this.lbPlotOpen) {
                this.lbPlotClose();
                return;
            }
            this.lbPlotOpen = true;
            return this._lbPlotLoad();
        },

        lbPlotClose() {
            this.lbPlotOpen = false;
        },

        _lbPlotReset() {
            this._lbPlotGen += 1;
            this.lbPlotOpen = false;
            this._lbPlotView = emptyPlotView();
        },

        async _lbPlotLoad() {
            const path = this.currentLightboxVideo?.path;
            if (!path) return;
            const gen = ++this._lbPlotGen;
            this._lbPlotView.path = path;
            this._lbPlotView.loading = true;
            this._lbPlotView.error = false;
            this._lbPlotView.plot = '';
            this._lbPlotView.original = '';
            this._lbPlotView.hasOriginal = false;
            this._lbPlotView.showing = 'plot';
            let ok = false;
            let data = null;
            try {
                const resp = await fetch(
                    `/api/showcase/video/plot?file_path=${encodeURIComponent(path)}`,
                );
                ok = resp.ok;
                data = await resp.json();
            } catch (e) {
                ok = false;
                data = null;
            }
            if (gen !== this._lbPlotGen) return;
            if (!ok || !data || data.success !== true) {
                this._lbPlotView.error = true;
                this._lbPlotView.loading = false;
                return;
            }
            this._lbPlotView.plot = data.plot || '';
            this._lbPlotView.original = data.original_plot || '';
            this._lbPlotView.hasOriginal = !!data.has_original;
            this._lbPlotView.loading = false;
        },

        lbPlotToggleOriginal() {
            const view = this._lbPlotView;
            if (!view.hasOriginal) return;
            view.showing = view.showing === 'plot' ? 'original' : 'plot';
        },

        async lbPlotTranslate() {
            const video = this.currentLightboxVideo;
            if (!video || !video.path) return;
            const view = this._lbPlotView;
            if (view.loading || view.error || !view.plot) return;
            const path = video.path;
            if (this._lbPlotInFlight[path]) return;
            this._lbPlotInFlight[path] = true;
            const sourceText = view.showing === 'original' ? (view.original || '') : view.plot;
            const isRetranslate = view.showing === 'original';
            const snapshot = { plot: view.plot, original: view.original || '' };
            try {
                let trData;
                try {
                    const trResp = await fetch('/api/translate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            text: sourceText,
                            mode: 'translate',
                            actors: (video.actresses || '').split(',').map((a) => a.trim()).filter(Boolean),
                            number: video.number || '',
                        }),
                    });
                    if (!trResp.ok) throw new Error(`HTTP ${trResp.status}`);
                    trData = await trResp.json();
                } catch (e) {
                    this.showToast(window.t(translateFailureToastKey(undefined)), 'error');
                    return;
                }
                if (trData.skipped === true) {
                    this.showToast(window.t('showcase.lightbox.plot_already_zh'), 'info');
                    return;
                }
                if (trData.success !== true || typeof trData.result !== 'string' || !trData.result) {
                    this.showToast(window.t(translateFailureToastKey(trData.reason)), 'error');
                    return;
                }
                const translated = trData.result;
                if (sameAfterNormalize(translated, sourceText)) {
                    this.showToast(window.t('showcase.lightbox.plot_already_zh'), 'info');
                    return;
                }
                const body = { file_path: path, plot: translated };
                if (isRetranslate) {
                    body.original_plot = view.original || '';
                }
                let data;
                try {
                    const resp = await fetch('/api/showcase/video/plot', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    data = await resp.json();
                } catch (e) {
                    this.showToast(window.t('showcase.lightbox.plot_write_failed'), 'error');
                    return;
                }
                if (data.success === true) {
                    this._lbPlotApply(view, data);
                    this.showToast(window.t('showcase.lightbox.plot_translate_done'), 'success', LB_PLOT_UNDO_TOAST_MS, {
                        label: window.t('showcase.lightbox.plot_translate_undo'),
                        onClick: () => this._lbPlotUndo(path, snapshot),
                    });
                } else {
                    const key = data.error === 'no_nfo' ? 'plot_no_nfo' : 'plot_write_failed';
                    this.showToast(window.t(`showcase.lightbox.${key}`), 'error');
                }
            } finally {
                delete this._lbPlotInFlight[path];
            }
        },

        _lbPlotApply(view, data) {
            view.plot = data.plot || '';
            view.original = data.original_plot || '';
            view.hasOriginal = !!data.has_original;
            view.showing = 'plot';
            view.loading = false;
            view.error = false;
        },

        async _lbPlotUndo(path, snapshot) {
            try {
                const resp = await fetch('/api/showcase/video/plot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: path,
                        plot: snapshot.plot,
                        original_plot: snapshot.original,
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success !== true) throw new Error(data.error || 'API failed');
                if (this._lbPlotView.path === path) {
                    this._lbPlotApply(this._lbPlotView, data);
                }
                this.showToast(window.t('showcase.lightbox.plot_translate_undone'), 'success');
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.plot_write_failed'), 'error');
            }
        },
    };
}
