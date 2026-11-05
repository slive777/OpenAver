// 整理與改名的舞台 scene（TASK-191a-T5 stub；T8 換成真畫面）。
// 介面：mount(root) 第一次成功啟動時呼叫一次；layout(canvas, scale) 量位置（畫布內座標）；
// render(v) 純函式畫面；cursorKeyframes 交給 cursorAt() 由 scene 自己畫游標（引擎不畫）。
import { stepOf } from './stage-math.js';
import { txt, css } from './stage-engine.js';

let num = null;
let stub = null;

export const scene = {
    mount(root) {
        num = root.querySelector('.hs-stub-num');
        stub = root.querySelector('.hs-stub');
    },
    layout() {},
    render(v) {
        txt(num, String(stepOf(v)));
        css(stub, '--hs-v', v.toFixed(3)); // e2e 的「一組畫面量」探針；T8 取代
    },
    cursorKeyframes: [],
};
