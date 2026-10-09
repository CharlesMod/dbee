const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let units = [], picked = new Set();
function draw() {
  const f = root.querySelector('#w-filter').value.toLowerCase();
  const rows = units.filter((u) => picked.has(u.name) || !f || u.name.toLowerCase().includes(f) || (u.about || '').toLowerCase().includes(f));
  root.querySelector('#w-list').innerHTML = rows.map((u, i) =>
    '<label class="svc"><input type="checkbox" data-n="' + esc(u.name) + '"' + (picked.has(u.name) ? ' checked' : '') + '><span>' + esc(u.name) +
    '</span><span class="st ' + u.state + '">' + u.state + '</span></label>').join('') || '<p class="hint">No service matches.</p>';
  root.querySelectorAll('#w-list input').forEach((b) => { b.onchange = () => { b.checked ? picked.add(b.dataset.n) : picked.delete(b.dataset.n); count(); }; });
  count();
}
function count() { root.querySelector('#w-count').textContent = picked.size + ' selected of ' + units.length + ' found'; }
function render(d, answers) {
  answers = answers || {};
  units = d.units || [];
  picked = new Set(answers.watch || []);
  const e = root.querySelector('#w-err');
  e.hidden = !d.error; e.textContent = d.error || '';
  const whole = root.querySelector('#w-whole');
  whole.checked = !!answers.whole_machine || (!!d.error && picked.size === 0);
  root.querySelector('#w-health').value = answers.health || '';
  const flip = () => { root.querySelector('#w-pick').style.opacity = whole.checked ? .45 : 1; };
  whole.onchange = flip; flip();
  root.querySelector('#w-filter').oninput = draw;
  draw();
}
function collect() {
  return { whole_machine: root.querySelector('#w-whole').checked, watch: Array.from(picked), health: root.querySelector('#w-health').value.trim() };
}
