/**
 * Spotlight Tutorial - 新手引導系統
 */
class SpotlightTutorial {
    constructor() {
        this.currentStep = 0;
        this.steps = [
            {
                id: 'search',
                target: '.spotlight-search',
                title: window.t('tutorial.step1_title'),
                content: window.t('tutorial.step1_content'),
                position: 'bottom'
            },
            {
                id: 'files',
                target: '#btnAddFiles',
                title: window.t('tutorial.step2_title'),
                content: window.t('tutorial.step2_content'),
                position: 'right'
            },
            {
                id: 'scanner',
                target: '#sidebar a[href="/scanner"]',
                title: window.t('tutorial.step3_title'),
                content: window.t('tutorial.step3_content'),
                position: 'right'
            },
            {
                id: 'settings',
                target: '#sidebar a[href="/settings"]',
                title: window.t('tutorial.step4_title'),
                content: window.t('tutorial.step4_content'),
                position: 'right'
            },
            {
                id: 'samples',
                target: '#emptyState',
                title: window.t('tutorial.step5_title'),
                content: window.t('tutorial.step5_content'),
                position: 'bottom',
                large: true
            }
        ];
        this.isActive = false;
        this.storageKey = 'openaver_tutorial_completed';
    }

    async shouldShow() {
        // 檢查後端狀態（持久化）
        try {
            const resp = await fetch('/api/tutorial-status');
            const data = await resp.json();
            if (data.success) {
                return !data.completed;
            }
        } catch (e) {
            console.warn('Tutorial API failed, fallback to localStorage');
        }
        // Fallback 到 localStorage（瀏覽器模式備用）
        return !localStorage.getItem(this.storageKey);
    }

    start() {
        if (this.isActive) return;
        this.isActive = true;
        this.currentStep = 0;
        this.createOverlay();
        this.showStep(0);
    }

    restart() {
        this.start();
    }

    createOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'tutorialOverlay';
        overlay.className = 'tutorial-overlay';
        overlay.innerHTML = `
            <div class="tutorial-spotlight" id="tutorialSpotlight"></div>
            <div class="tutorial-card" id="tutorialCard">
                <div class="tutorial-card-header">
                    <h5 id="tutorialTitle"></h5>
                    <button class="tutorial-close" id="tutorialClose" title="${window.t('tutorial.close')}">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
                <div class="tutorial-card-body">
                    <p id="tutorialContent"></p>
                </div>
                <div class="tutorial-card-footer">
                    <span class="tutorial-progress" id="tutorialProgress"></span>
                    <div class="tutorial-actions">
                        <button class="btn btn-sm btn-outline-secondary" id="tutorialSkip">${window.t('tutorial.skip')}</button>
                        <button class="btn btn-sm btn-primary" id="tutorialNext">${window.t('tutorial.next')}</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        document.getElementById('tutorialNext').addEventListener('click', () => this.nextStep());
        document.getElementById('tutorialSkip').addEventListener('click', () => this.skip());
        document.getElementById('tutorialClose').addEventListener('click', () => this.skip());
        overlay.addEventListener('click', (e) => {
            if (e.target.id === 'tutorialOverlay') this.skip();
        });
    }

    showStep(stepIndex) {
        if (stepIndex >= this.steps.length) {
            this.complete();
            return;
        }

        const step = this.steps[stepIndex];
        const target = document.querySelector(step.target);

        if (!target) {
            console.warn(`Tutorial target not found: ${step.target}`);
            this.nextStep();
            return;
        }

        // 檢查目標是否在 sidebar 內
        const sidebar = document.getElementById('sidebar');
        const isInSidebar = sidebar && sidebar.contains(target);
        const overlay = document.getElementById('tutorialOverlay');
        const spotlight = document.getElementById('tutorialSpotlight');

        if (isInSidebar) {
            // Sidebar Mode：遮罩只覆蓋主內容區
            overlay.classList.add('sidebar-mode');
            const sidebarRect = sidebar.getBoundingClientRect();
            overlay.style.left = `${sidebarRect.right}px`;
            spotlight.style.display = 'none';
            // 高亮目標連結
            target.style.outline = '3px solid var(--accent, #5ac8fa)';
            target.style.outlineOffset = '4px';
        } else {
            // 正常 Spotlight Mode
            overlay.classList.remove('sidebar-mode');
            overlay.style.left = '';
            spotlight.style.display = '';
            // 清除之前的高亮
            this.clearHighlights();
            this.positionSpotlight(target);
        }

        document.getElementById('tutorialTitle').textContent = step.title;
        document.getElementById('tutorialContent').innerHTML = step.content;

        // 大視窗模式
        const card = document.getElementById('tutorialCard');
        if (step.large) {
            card.classList.add('large');
        } else {
            card.classList.remove('large');
        }

        document.getElementById('tutorialProgress').textContent = `${stepIndex + 1} / ${this.steps.length}`;

        const btnNext = document.getElementById('tutorialNext');
        btnNext.innerHTML = stepIndex === this.steps.length - 1 ? window.t('tutorial.done') : window.t('tutorial.next');

        this.positionCard(target, step.position, isInSidebar);

        requestAnimationFrame(() => {
            document.getElementById('tutorialOverlay').classList.add('active');
        });
    }

    clearHighlights() {
        this.steps.forEach(s => {
            const el = document.querySelector(s.target);
            if (el) {
                el.style.outline = '';
                el.style.outlineOffset = '';
            }
        });
    }

    positionSpotlight(target) {
        const rect = target.getBoundingClientRect();
        const spotlight = document.getElementById('tutorialSpotlight');
        const padding = 8;

        spotlight.style.top = `${rect.top - padding}px`;
        spotlight.style.left = `${rect.left - padding}px`;
        spotlight.style.width = `${rect.width + padding * 2}px`;
        spotlight.style.height = `${rect.height + padding * 2}px`;
    }

    positionCard(target, position, isInSidebar = false) {
        const rect = target.getBoundingClientRect();
        const card = document.getElementById('tutorialCard');
        const gap = 20;

        card.style.position = 'fixed';
        card.style.top = 'auto';
        card.style.left = 'auto';
        card.style.right = 'auto';
        card.style.bottom = 'auto';

        if (isInSidebar) {
            // Sidebar 內的元素：卡片放在 sidebar 右邊，垂直置中偏上
            const sidebar = document.getElementById('sidebar');
            const sidebarRect = sidebar.getBoundingClientRect();
            card.style.top = `${Math.max(rect.top, 100)}px`;
            card.style.left = `${sidebarRect.right + gap}px`;
        } else {
            switch (position) {
                case 'bottom':
                    card.style.top = `${rect.bottom + gap}px`;
                    card.style.left = `${rect.left}px`;
                    break;
                case 'right':
                    card.style.top = `${rect.top}px`;
                    card.style.left = `${rect.right + gap}px`;
                    break;
            }
        }

        // 確保不超出視窗
        requestAnimationFrame(() => {
            const cardRect = card.getBoundingClientRect();
            if (cardRect.right > window.innerWidth) {
                card.style.left = `${window.innerWidth - cardRect.width - 20}px`;
            }
            if (cardRect.bottom > window.innerHeight) {
                card.style.top = `${window.innerHeight - cardRect.height - 20}px`;
            }
        });
    }

    nextStep() {
        this.currentStep++;
        this.showStep(this.currentStep);
    }

    skip() {
        this.complete(false);
    }

    async complete(markComplete = true) {
        if (markComplete) {
            // 寫入後端（持久化，PyWebView 環境）
            try {
                await fetch('/api/tutorial-completed', { method: 'POST' });
            } catch (e) {
                console.warn('Tutorial API failed, fallback to localStorage');
            }
            // 同時寫入 localStorage（瀏覽器模式備用）
            localStorage.setItem(this.storageKey, 'true');
        }

        // 清除所有高亮樣式
        this.clearHighlights();

        const overlay = document.getElementById('tutorialOverlay');
        if (overlay) {
            overlay.classList.remove('active');
            overlay.style.left = '';
            setTimeout(() => overlay.remove(), 300);
        }
        this.isActive = false;
    }
}

// 全域實例
window.SpotlightTutorial = new SpotlightTutorial();

// 首次啟動自動觸發 + URL 參數觸發
document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);

    // 檢查 URL 參數觸發（從其他頁面導向）
    if (urlParams.get('tutorial') === 'restart') {
        // 重置後端狀態
        try {
            await fetch('/api/tutorial-reset', { method: 'POST' });
        } catch (e) {
            console.warn('Tutorial reset API failed');
        }
        localStorage.removeItem('openaver_tutorial_completed');
        setTimeout(() => {
            window.SpotlightTutorial.start();
        }, 1000);
        return;
    }

    // 首次啟動自動觸發（僅 /search 頁面）
    if (window.location.pathname === '/search' || window.location.pathname === '/') {
        setTimeout(async () => {
            if (await window.SpotlightTutorial.shouldShow()) {
                window.SpotlightTutorial.start();
            }
        }, 1000);
    }
});
