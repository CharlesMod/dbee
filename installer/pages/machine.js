function render(d) {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  root.querySelector('#m-rows').innerHTML = d.rows.map((r) => '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>').join('');
  root.querySelector('#m-hive').textContent = d.hive;
  const n = root.querySelector('#m-note');
  n.hidden = !d.note; n.textContent = d.note || '';
}
