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
    document.getElementById(id).classList.remove('hidden');
}
function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

// 点击遮罩关闭模态框
document.addEventListener('click', (e) => {
    if (e.target.classList && e.target.classList.contains('modal-overlay')) {
        e.target.classList.add('hidden');
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
