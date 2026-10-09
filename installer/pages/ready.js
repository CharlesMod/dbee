function render(d) {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  root.querySelector('#r-items').innerHTML = (d.items || []).map((i) => '<li>' + esc(i) + '</li>').join('');
  root.querySelector('#r-rows').innerHTML = (d.rows || []).map((r) => '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>').join('');
  const n = root.querySelector('#r-err'); n.hidden = !d.error; n.textContent = d.error || '';
}
