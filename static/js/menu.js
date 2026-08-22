let categories = [];
let products = [];
let activeAudience = null;
let activeCategory = null;

const $ = selector => document.querySelector(selector);
const audienceNames = { defectologists: 'Дефектологам', speech_therapists: 'Логопедам', school: 'Подготовка к школе' };
const categoryOrder = {
  defectologists: ['Диагностика', 'Дидактические игры', 'Программы коррекционных курсов', 'Документы Дефектолога', 'Рабочие листы', 'Рабочие тетради', 'Вебинары'],
  speech_therapists: ['Диагностика', 'Дидактические игры', 'Документы Логопеда', 'Программы коррекционных курсов', 'Рабочие листы', 'Рабочие тетради'],
  school: ['Чтение', 'Буквы и слоги', 'Математический счет', 'Развитие графо-моторных навыков', 'Подготовка руки к письму', 'Диагностика готовности к школе', 'Геометрический материал']
};
async function api(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw new Error(data.message || 'Ошибка запроса'); return data; }
function esc(value) { return String(value).replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function renderAudienceMenus() {
  const element = $('#audienceMenus');
  element.innerHTML = Object.entries(audienceNames).map(([key, name], index) => `<button class="audience-card ${activeAudience === key ? 'active' : ''}" data-audience="${key}"><span class="audience-number">0${index + 1}</span><strong>${name}</strong></button>`).join('');
  element.querySelectorAll('[data-audience]').forEach(button => button.addEventListener('click', () => { activeAudience = button.dataset.audience; activeCategory = null; renderAudienceMenus(); renderCategories(); renderProducts(); }));
}
function renderCategories() {
  const element = $('#categoryFilters');
  const names = categoryOrder[activeAudience] || [];
  const unique = new Map();
  categories.filter(category => category.audience === activeAudience && names.includes(category.name)).forEach(category => {
    if (!unique.has(category.name)) unique.set(category.name, category);
  });
  const available = [...unique.values()].sort((a, b) => names.indexOf(a.name) - names.indexOf(b.name));
  if (!activeAudience) { element.innerHTML = ''; return; }
  element.innerHTML = available.map(category => `<button class="category-card ${activeCategory === category.id ? 'active' : ''}" data-category="${category.id}"><strong>${esc(category.name)}</strong></button>`).join('');
  element.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => { activeCategory = button.dataset.category === 'all' ? null : Number(button.dataset.category); renderCategories(); renderProducts(); }));
}
function renderProducts() {
  const element = $('#products');
  if (!activeAudience) { element.innerHTML = ''; return; }
  const list = products.filter(product => product.audience === activeAudience && (activeCategory === null || product.category_id === activeCategory));
  if (!list.length) { element.innerHTML = '<div class="loading">В этой категории пока нет материалов.</div>'; return; }
  element.innerHTML = list.map(product => `<article class="product-card"><div class="product-image">${product.image_path ? `<img src="/uploads/${encodeURIComponent(product.image_path)}" alt="">` : '<div class="placeholder">✦</div>'}</div><div class="product-body"><div class="product-meta">${esc(product.category_name || 'Материал')}</div><h3>${esc(product.title)}</h3><p>${esc(product.description || 'Готовый материал для работы.')}</p>${product.price ? `<div class="price">${esc(product.price)} ₽</div>` : ''}<button class="btn btn-primary" onclick="openOrder(${product.id})">Подробнее / заказать</button></div></article>`).join('');
}
window.openOrder = id => { const product = products.find(item => item.id === id); if (!product) return; $('#modalProduct').textContent = product.title; $('#productInput').value = product.title; $('#formMessage').textContent = ''; $('#formMessage').className = 'form-message'; $('#orderModal').classList.add('open'); $('#orderModal').setAttribute('aria-hidden', 'false'); };
function closeModal() { $('#orderModal').classList.remove('open'); $('#orderModal').setAttribute('aria-hidden', 'true'); }
document.querySelectorAll('[data-close]').forEach(item => item.addEventListener('click', closeModal));
$('#orderForm').addEventListener('submit', async event => { event.preventDefault(); const form = new FormData(event.target); const message = $('#formMessage'); try { await api('/api/new_order', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.get('name'), contact: form.get('contact'), product: $('#productInput').value }) }); message.textContent = 'Заявка принята. Мы свяжемся с вами.'; message.className = 'form-message success'; event.target.reset(); } catch (error) { message.textContent = error.message; message.className = 'form-message error'; } });
(async () => { try { [categories, products] = await Promise.all([api('/api/categories'), api('/api/products')]); renderAudienceMenus(); renderCategories(); renderProducts(); const settings = await api('/api/settings'); if (settings.phone || settings.email || settings.tg_link) $('#contactLinks').innerHTML = [settings.phone ? `<a href="tel:${esc(settings.phone)}">${esc(settings.phone)}</a>` : '', settings.email ? `<a href="mailto:${esc(settings.email)}">${esc(settings.email)}</a>` : '', settings.tg_link ? `<a href="${esc(settings.tg_link)}" target="_blank" rel="noopener">Telegram ${esc(settings.tg_username || '')}</a>` : ''].join(''); if (settings.hero_image_path) $('#hero').style.backgroundImage = `url('/uploads/${encodeURIComponent(settings.hero_image_path)}')`; } catch (error) { $('#products').innerHTML = '<div class="loading">Не удалось загрузить каталог.</div>'; } $('#year').textContent = new Date().getFullYear(); })();
