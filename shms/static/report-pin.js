(() => {
  const form = document.querySelector('#hazard-report');
  const area = form.elements.area_id;
  const x = form.elements.x;
  const y = form.elements.y;
  const map = document.querySelector('#report-map');
  const bounds = document.querySelector('#pin-bounds');
  const marker = document.querySelector('#picked-point');
  const status = document.querySelector('#pin-status');
  const clear = document.querySelector('#clear-pin');
  const picker = document.querySelector('#pin-picker');

  function updatePoint() {
    x.required = y.value !== '';
    y.required = x.value !== '';
    const valid = x.value !== '' && y.value !== '' && x.validity.valid && y.validity.valid;
    marker.style.display = valid ? '' : 'none';
    if (valid) marker.setAttribute('transform', `translate(${x.valueAsNumber} ${y.valueAsNumber})`);
    clear.disabled = x.value === '' && y.value === '';
    status.textContent = valid ? `Pin at X ${x.value}, Y ${y.value}.` :
      `X ${x.min}–${x.max}, Y ${y.min}–${y.max} in this unit.`;
  }
  function updateArea() {
    const unit = area.selectedOptions[0]?.dataset;
    picker.hidden = !unit?.w;
    if (picker.hidden) return;
    const left = Number(unit.x), top = Number(unit.y), w = Number(unit.w), h = Number(unit.h);
    x.min = left;
    x.max = left + w;
    y.min = top;
    y.max = top + h;
    map.setAttribute('viewBox', `${left - 5} ${top - 5} ${w + 10} ${h + 10}`);
    for (const [attr, value] of Object.entries({x: left, y: top, width: w, height: h})) {
      bounds.setAttribute(attr, value);
    }
    updatePoint();
  }
  function clearPoint() {
    x.value = '';
    y.value = '';
    updatePoint();
  }
  area.addEventListener('change', () => { clearPoint(); updateArea(); });
  clear.addEventListener('click', clearPoint);
  for (const input of [x, y]) {
    input.addEventListener('input', updatePoint);
    input.addEventListener('invalid', () => { picker.open = true; });
  }
  map.addEventListener('click', event => {
    event.preventDefault();
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(map.getScreenCTM().inverse());
    const px = Math.round(p.x), py = Math.round(p.y);
    if (px < Number(x.min) || px > Number(x.max) || py < Number(y.min) || py > Number(y.max)) {
      status.textContent = 'Choose a point inside the outlined unit.';
      return;
    }
    x.value = px;
    y.value = py;
    updatePoint();
  });
  form.addEventListener('submit', () => {
    const submit = form.querySelector('button[type=submit]');
    submit.disabled = true;
    submit.textContent = 'Analysing photo…';
  });
  map.removeAttribute('hidden');
  clear.hidden = false;
  updateArea();
})();
