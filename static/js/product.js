const mainImage = document.querySelector('#mainProductImage');
const thumbnails = [...document.querySelectorAll('.thumbnail')];
let currentImage = 0;
function showImage(index) {
  if (!mainImage || !thumbnails.length) return;
  currentImage = (index + thumbnails.length) % thumbnails.length;
  mainImage.src = thumbnails[currentImage].dataset.image;
  thumbnails.forEach((thumbnail, i) => thumbnail.classList.toggle('active', i === currentImage));
}
thumbnails.forEach((thumbnail, index) => thumbnail.addEventListener('click', () => showImage(index)));
document.querySelector('.gallery-prev')?.addEventListener('click', () => showImage(currentImage - 1));
document.querySelector('.gallery-next')?.addEventListener('click', () => showImage(currentImage + 1));
document.querySelector('#productOrderForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  const message = document.querySelector('#orderMessage');
  try {
    const response = await fetch('/api/new_order', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name: form.get('name'), contact: form.get('contact'), product: document.title }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || 'Ошибка отправки');
    message.textContent = 'Заявка принята.';
    message.className = 'form-message success';
    event.target.reset();
  } catch (error) { message.textContent = error.message; message.className = 'form-message error'; }
});
