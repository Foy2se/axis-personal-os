/* AXIS Personal OS 3.0 - 前端交互 + 主题管理 + PWA */

// ===================== 主题管理 =====================

function getEffectiveTheme() {
    const theme = localStorage.getItem('theme') || 'auto';
    if (theme === 'auto') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return theme;
}

function applyTheme() {
    const effective = getEffectiveTheme();
    if (effective === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    updateThemeButtons();
    updateMobileThemeBtn();
}

function setTheme(theme) {
    localStorage.setItem('theme', theme);
    applyTheme();
}

function toggleThemeQuick() {
    // 移动端快捷切换：light -> dark -> auto -> light
    const current = localStorage.getItem('theme') || 'auto';
    const next = current === 'light' ? 'dark' : current === 'dark' ? 'auto' : 'light';
    setTheme(next);
}

function updateThemeButtons() {
    const current = localStorage.getItem('theme') || 'auto';
    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-theme-val') === current);
    });
}

function updateMobileThemeBtn() {
    const btn = document.getElementById('mobile-theme-btn');
    if (!btn) return;
    const theme = localStorage.getItem('theme') || 'auto';
    const icons = { light: '🌞', dark: '🌙', auto: '🖥️' };
    btn.textContent = icons[theme];
}

// 监听系统主题变化（auto模式下自动切换）
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (localStorage.getItem('theme') === 'auto' || !localStorage.getItem('theme')) {
        applyTheme();
    }
});

// ===================== PWA Service Worker（已禁用） =====================
// SW 是加载卡住的根因，彻底移除注册逻辑
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function(regs) {
        regs.forEach(function(r) { r.unregister(); });
    });
}

// ===================== 侧边栏 =====================

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const bottomNav = document.getElementById('bottom-nav');
    sidebar.classList.toggle('-translate-x-full');
    overlay.classList.toggle('hidden');
    if (bottomNav) bottomNav.classList.toggle('hidden');
}

// ===================== 模态框 =====================

function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('hidden');
}
function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('hidden');
}

// 点击遮罩关闭模态框
document.addEventListener('click', function(e) {
    if (e.target.classList && e.target.classList.contains('modal-overlay')) {
        e.target.classList.add('hidden');
    }
});

// 按 ESC 键关闭所有打开的模态框
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' || e.keyCode === 27) {
        document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(function(m) {
            m.classList.add('hidden');
        });
    }
});

// ===================== 星级评分 =====================

function setupStarRating(containerId, inputId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const hiddenInput = document.getElementById(inputId);
    const stars = container.querySelectorAll('.star');
    let currentValue = parseInt(hiddenInput.value) || 0;

    function render(value) {
        stars.forEach((star, index) => {
            star.classList.toggle('active', index < value);
        });
    }
    render(currentValue);

    stars.forEach((star, index) => {
        star.addEventListener('click', () => {
            currentValue = index + 1;
            hiddenInput.value = currentValue;
            render(currentValue);
        });
        star.addEventListener('mouseenter', () => {
            render(index + 1);
        });
    });
    container.addEventListener('mouseleave', () => {
        render(currentValue);
    });
}

// ===================== 工具函数 =====================

function confirmDelete(msg) {
    return confirm(msg || '确定删除吗？此操作不可撤销。');
}

// Ctrl+Enter 快捷提交
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        const form = e.target.closest('form');
        if (form) form.submit();
    }
});

// ESC 关闭模态框
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => m.classList.add('hidden'));
    }
});

// ===================== 初始化 =====================

document.addEventListener('DOMContentLoaded', () => {
    applyTheme();

    // 初始化所有星级评分
    document.querySelectorAll('[data-star-rating]').forEach(container => {
        const inputId = container.getAttribute('data-input-id');
        setupStarRating(container.id, inputId);
    });
});

// ===================== 提交反馈 / 防止重复提交 =====================
// 解决：操作无即时反馈、重复点击导致重复请求、操作后页面状态未及时刷新。
// 仅在客户端做"提交中"提示与防重复，不改变任何后端逻辑与页面结构。
(function () {
    function showBusy() {
        var el = document.getElementById('axis-busy');
        if (!el) {
            el = document.createElement('div');
            el.id = 'axis-busy';
            el.setAttribute('role', 'status');
            el.style.cssText = 'position:fixed;left:50%;top:14px;transform:translateX(-50%);' +
                'z-index:9999;background:var(--primary,#6366f1);color:#fff;padding:8px 14px;' +
                'border-radius:9999px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.2);' +
                'transition:opacity .15s;';
            el.textContent = '⏳ 处理中…';
            (document.body || document.documentElement).appendChild(el);
        }
        el.style.display = 'block';
        el.style.opacity = '1';
    }
    function hideBusy() {
        var el = document.getElementById('axis-busy');
        if (el) el.style.display = 'none';
    }

    window.__axisSubmitting = false;

    document.addEventListener('submit', function (e) {
        if (window.__axisSubmitting) { e.preventDefault(); return; }
        window.__axisSubmitting = true;
        showBusy();
        // 禁用提交按钮与自动提交的 select，给出即时反馈并防止重复请求
        var btn = e.submitter || (e.target && e.target.querySelector('button[type="submit"]'));
        if (btn && !btn.disabled) {
            if (!btn.dataset.__orig) btn.dataset.__orig = btn.textContent;
            btn.disabled = true;
            btn.textContent = '处理中…';
        }
        var statusSel = e.target && e.target.querySelector('select[name="status"]');
        if (statusSel) statusSel.disabled = true;
        // 兜底：若 8 秒内未完成导航（如校验失败被拦截），恢复可操作
        setTimeout(function () {
            window.__axisSubmitting = false;
            hideBusy();
            if (btn) { btn.disabled = false; if (btn.dataset.__orig) btn.textContent = btn.dataset.__orig; }
            if (statusSel) statusSel.disabled = false;
        }, 8000);
    }, true);

    // 新页面已就绪即隐藏提示
    window.addEventListener('DOMContentLoaded', hideBusy);
    window.addEventListener('pageshow', hideBusy);
})();
