const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let D = null;
function render(d, answers) {
  D = d; answers = answers || {};
  const want = answers.mind_kind === 'local' ? 'local:' + answers.model : (answers.mind_kind || '');
  const pre = want || (d.cards.find((c) => c.recommended) ? 'local:' + d.cards.find((c) => c.recommended).name : '');
  root.querySelector('#k-cards').innerHTML = d.cards.map((c) => {
    const lines = c.locked
      ? '<span>' + esc(c.reason) + '</span>'
      : '<span>' + esc(c.shape) + '. Context ' + c.ctx.toLocaleString() + ' tokens. ' +
        (c.already ? 'Already on this machine.' : 'Download ' + esc(c.size) + '.') + '</span>';
    return '<label class="choice' + (c.locked ? ' locked' : '') + '"><input type="radio" name="pick" value="local:' + esc(c.name) + '"' +
      (c.locked ? ' disabled' : '') + (pre === 'local:' + c.name && !c.locked ? ' checked' : '') + '><b style="display:inline">' + esc(c.label) +
      (c.recommended ? '<span class="tag">Recommended</span>' : '') + (c.already && !c.locked ? '<span class="tag have">on this machine</span>' : '') +
      '</b>' + '<span style="display:block;margin-top:2px">' + esc(c.why || '') + '</span>' + lines + '</label>';
  }).join('');
  const hive = d.hive.available
    ? '<label class="choice"><input type="radio" name="pick" value="hive"' + (pre === 'hive' ? ' checked' : '') + '><b style="display:inline">This Hive\'s minds</b>' +
      '<span style="display:block">Use the Hive\'s router; nothing is installed for the mind.</span></label>' +
      '<div class="sub" id="o-hive" hidden><label class="field">Court address</label><input type="text" id="hive-court" value="' + esc(answers.hive_court || d.hive.court) + '">' +
      '<label class="field">Model</label><input type="text" id="hive-model" value="' + esc(answers.hive_model || d.hive.model) + '"></div>'
    : '';
  root.querySelector('#k-others').innerHTML =
    '<label class="choice"><input type="radio" name="pick" value="url"' + (pre === 'url' ? ' checked' : '') + '><b style="display:inline">A model I already serve</b>' +
    '<span style="display:block">Any OpenAI-compatible server: Ollama, LM Studio, vLLM or llama-server. One test call is made before you can go on.</span></label>' +
    '<div class="sub" id="o-url" hidden><label class="field">Server address</label><input type="text" id="url-addr" placeholder="http://127.0.0.1:11434/v1" value="' + esc(answers.mind_url || '') + '">' +
    '<label class="field">Model name (optional)</label><input type="text" id="url-model" value="' + esc(answers.mind_model || '') + '"></div>' +
    '<label class="choice"><input type="radio" name="pick" value="claude"' + (pre === 'claude' ? ' checked' : '') + '><b style="display:inline">Claude</b>' +
    '<span style="display:block">A hosted mind. The key is kept in a file only you can read and is never shown again.</span></label>' +
    '<div class="sub" id="o-claude" hidden><label class="field">API key' + (d.claude.saved ? ' (one is saved; leave blank to keep it)' : '') + '</label>' +
    '<input type="password" id="claude-key" autocomplete="off"></div>' + hive;
  const sync = () => {
    const v = (root.querySelector('input[name=pick]:checked') || {}).value || '';
    ['url', 'claude', 'hive'].forEach((k) => { const e = root.querySelector('#o-' + k); if (e) e.hidden = v !== k; });
  };
  root.querySelectorAll('input[name=pick]').forEach((r) => { r.onchange = sync; });
  sync();
}
function collect() {
  const v = (root.querySelector('input[name=pick]:checked') || {}).value || '';
  const val = (id) => { const e = root.querySelector(id); return e ? e.value.trim() : ''; };
  if (v.startsWith('local:')) return { mind_kind: 'local', model: v.slice(6) };
  if (v === 'url') return { mind_kind: 'url', mind_url: val('#url-addr'), mind_model: val('#url-model') };
  if (v === 'claude') return { mind_kind: 'claude', claude_key: val('#claude-key') };
  if (v === 'hive') return { mind_kind: 'hive', hive_court: val('#hive-court'), hive_model: val('#hive-model') };
  return {};
}
