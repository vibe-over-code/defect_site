(async () => {
  try {
    const response = await fetch('/api/settings');
    const settings = await response.json();
    const fit = settings.card_image_fit === 'contain' ? 'contain' : 'cover';
    document.documentElement.style.setProperty('--card-image-fit', fit);
  } catch (error) {
    // The default is cover, so the catalog remains usable if settings are unavailable.
  }
})();
