// Report form: photo check before upload, "Analysing…" state, and the optional device location.
(() => {
  const form = document.querySelector('#hazard-report');
  if (!form) return;
  const photo = form.querySelector('#photo');
  const photoStatus = document.querySelector('#photo-status');
  const maxMb = Number(photo.dataset.maxMb || 30);
  const help = photoStatus.textContent;

  photo.addEventListener('change', () => {
    const file = photo.files[0];
    photo.setCustomValidity('');
    if (!file) { photoStatus.textContent = help; return; }
    const mb = file.size / (1024 * 1024);
    if (mb > maxMb) {
      const msg = `This photo is ${mb.toFixed(1)} MB; the limit is ${maxMb} MB. Choose a smaller copy or take a screenshot of it.`;
      photo.setCustomValidity(msg);
      photoStatus.textContent = msg;
      photoStatus.classList.add('err');
      return;
    }
    photoStatus.classList.remove('err');
    photoStatus.textContent = `Selected: ${file.name} (${mb.toFixed(1)} MB).`;
  });

  form.addEventListener('submit', () => {
    if (!form.checkValidity()) return;
    const box = document.querySelector('#analysing');
    box.hidden = false;
    box.scrollIntoView({ block: 'nearest' });
  });

  // Browser location: only after the reporter taps the button; needs https or localhost (a secure context).
  const button = document.querySelector('#use-location');
  const status = document.querySelector('#location-status');
  const lat = document.querySelector('#device-lat');
  const lon = document.querySelector('#device-lon');
  const acc = document.querySelector('#device-accuracy');
  if (!('geolocation' in navigator)) {
    status.textContent = 'This browser cannot share a location. You can still report by area and map pin.';
    return;
  }
  if (!window.isSecureContext) {
    status.textContent = 'Location sharing needs a secure (https) connection. You can still report by area and map pin.';
    return;
  }
  button.hidden = false;
  button.addEventListener('click', () => {
    button.disabled = true;
    status.textContent = 'Asking your device for its location…';
    navigator.geolocation.getCurrentPosition(pos => {
      lat.value = pos.coords.latitude.toFixed(6);
      lon.value = pos.coords.longitude.toFixed(6);
      acc.value = Math.round(pos.coords.accuracy);
      status.textContent = `Location added (accurate to about ${Math.round(pos.coords.accuracy)} m). It is used only if the photo has no GPS.`;
      button.textContent = 'Update my location';
      button.disabled = false;
    }, err => {
      const reasons = {
        1: 'Location permission was refused. You can allow it in the browser settings, or report by area and map pin.',
        2: 'Your device could not find its location. Try again outdoors, or report by area and map pin.',
        3: 'Finding your location took too long. Try again, or report by area and map pin.',
      };
      status.textContent = reasons[err.code] || 'Location is not available. Report by area and map pin.';
      button.disabled = false;
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  });
})();
