import { pathToDisplay } from '../components/path-utils.js';
import { copyText } from './clipboard.js';

const SEP = '\t';

export function buildCopyText(items) {
    const header = ['number', 'path', 'reason'].map(key => window.t(`common.number_drilldown.copy_col_${key}`)).join(SEP);
    return [header, ...items.map(item => [item.number || '', pathToDisplay(item.path || ''), item.reason || ''].join(SEP))].join('\n');
}

export async function copyItemList(items) {
    const text = buildCopyText(items);
    const ok = await copyText(text);
    return { ok, text, count: items.length };
}
