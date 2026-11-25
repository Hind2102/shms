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

  let polygon = [];
  function inside(px, py) {  // point in polygon, outline counts as inside (same rule as the server)
    let hit = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const [x1, y1] = polygon[i], [x2, y2] = polygon[j];
      const onEdge = (px - x1) * (y2 - y1) === (py - y1) * (x2 - x1) &&
        Math.min(x1, x2) <= px && px <= Math.max(x1, x2) && Math.min(y1, y2) <= py && py <= Math.max(y1, y2);
      if (onEdge) return true;
      if ((y1 > py) !== (y2 > py) && px < x1 + (py - y1) * (x2 - x1) / (y2 - y1)) hit = !hit;
    }
    return hit;
  }
  function updatePoint() {
    x.required = y.value !== '';
    y.required = x.value !== '';
    const valid = x.value !== '' && y.value !== '' && x.validity.valid && y.validity.valid && inside(x.valueAsNumber, y.valueAsNumber);
    marker.style.display = valid ? '' : 'none';
    if (valid) marker.setAttribute('transform', `translate(${x.valueAsNumber} ${y.valueAsNumber})`);
    clear.disabled = x.value === '' && y.value === '';
    status.textContent = valid ? `Pin at X ${x.value}, Y ${y.value}.` :
      `X ${x.min}–${x.max}, Y ${y.min}–${y.max} inside the outlined zone.`;
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
    const pad = Math.max(20, Math.round(Math.max(w, h) * 0.06));
    map.setAttribute('viewBox', `${left - pad} ${top - pad} ${w + 2 * pad} ${h + 2 * pad}`);
    polygon = unit.points.split(' ').map(p => p.split(',').map(Number));
    bounds.setAttribute('points', unit.points);
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
    if (!inside(px, py)) {
      status.textContent = 'Choose a point inside the outlined zone.';
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
