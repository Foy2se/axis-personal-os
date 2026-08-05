/** Tailwind 构建配置：将运行时编译改为构建期静态产出 */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js"
  ],
  // 与 app 现有机制对齐：应用用 [data-theme="dark"] 切换暗色，
  // 这里让 Tailwind 的 dark: 变体也认这个选择器（与原 play CDN 行为兼容）
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {}
  },
  // 兜底：JS 动态切换的少量类，确保一定产出
  safelist: [
    'hidden', 'block', 'flex', 'grid', 'inline-flex',
    '-translate-x-full', 'translate-x-0'
  ],
  plugins: []
};
