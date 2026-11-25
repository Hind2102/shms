(() => {
  const svg = document.getElementById('plan');
  const box = svg.viewBox.baseVal;
  const width = box.width, height = box.height;
  let x = 0, y = 0, w = width, h = height;
  const bound = (value, max) => Math.max(0, Math.min(max, value));
  function render() {
    x = bound(x, width - w);
    y = bound(y, height - h);
    svg.setAttribute('viewBox', [x, y, w, h].join(' '));
    svg.classList.toggle('is-zoomed', w < width);
  }
  function zoom(factor, cx = x + w / 2, cy = y + h / 2) {
    const next = Math.max(width * 0.15, Math.min(width, w * factor));
    x = cx - (cx - x) * next / w;
    y = cy - (cy - y) * next / w;
    w = next;
    h = w * height / width;
    render();
  }
  function pan(direction) {
    const motion = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]}[direction];
    x += motion[0] * w / 5;
    y += motion[1] * h / 5;
    render();
  }
  function reset() { w = width; h = height; x = y = 0; render(); }
  function changeZoom(action) {
    if (action === 'reset') reset();
    else zoom(action === 'in' ? 0.7 : 1 / 0.7);
  }
  document.querySelectorAll('[data-zoom]').forEach(b => b.addEventListener('click', () => changeZoom(b.dataset.zoom)));
  document.querySelectorAll('[data-pan]').forEach(b => b.addEventListener('click', () => pan(b.dataset.pan)));
  svg.addEventListener('keydown', e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key.startsWith('Arrow')) pan(e.key.slice(5).toLowerCase());
    else if (['+', '='].includes(e.key)) zoom(0.7);
    else if (e.key === '-') zoom(1 / 0.7);
    else if (e.key === 'Home') reset();
    else return;
    e.preventDefault();
  });
  function point(e) {
    return new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
  }
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const p = point(e);
    zoom(e.deltaY < 0 ? 0.85 : 1 / 0.85, p.x, p.y);
  }, {passive: false});
  let drag = null, moved = false;
  svg.addEventListener('pointerdown', e => {
    moved = false;
    if (w < width && e.button === 0) drag = {id: e.pointerId, x: e.clientX, y: e.clientY, vx: x, vy: y};
  });
  svg.addEventListener('pointermove', e => {
    if (!drag || drag.id !== e.pointerId) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;
    moved = true;
    svg.setPointerCapture(e.pointerId);
    const scale = svg.getScreenCTM().a;
    x = drag.vx - dx / scale;
    y = drag.vy - dy / scale;
    render();
  });
  window.addEventListener('pointerup', () => { drag = null; });
  svg.addEventListener('pointercancel', () => { drag = null; });
  svg.addEventListener('click', e => {
    if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; }
  }, true);
})();
