let diskChart = null
let logsChart = null

function esc (s) { return String(s) }

function setStatus (msg) {
  document.getElementById('status').textContent = msg
}

function setErrors (msg) {
  const box = document.getElementById('errors')
  box.textContent = ''
  if (msg) {
    const p = document.createElement('p')
    p.textContent = msg
    p.style.color = 'var(--err)'
    box.appendChild(p)
  }
}

function badge (status) {
  const s = document.createElement('span')
  s.className = `badge ${(status || 'info').toLowerCase()}`
  s.textContent = (status || 'info').toUpperCase()
  return s
}

function initTheme () {
  const btn = document.getElementById('theme')
  let stored = null
  try { stored = localStorage.getItem('hermes-theme') } catch { /* ignore */ }
  const prefersHC = window.matchMedia && window.matchMedia('(prefers-contrast: more)').matches
  const apply = (hc) => {
    if (hc) document.body.setAttribute('data-theme', 'high-contrast')
    else document.body.removeAttribute('data-theme')
    btn.textContent = `High-contrast: ${hc ? 'on' : 'off'}`
    btn.setAttribute('aria-pressed', hc ? 'true' : 'false')
    try { localStorage.setItem('hermes-theme', hc ? 'high-contrast' : 'default') } catch { /* ignore */ }
  }
  apply(stored === 'high-contrast' || (!stored && prefersHC))
  btn.addEventListener('click', () => {
    apply(document.body.getAttribute('data-theme') !== 'high-contrast')
    btn.focus()
  })
}

function renderChecks (checks) {
  const box = document.getElementById('checks')
  box.innerHTML = ''
  if (!checks || !checks.length) {
    box.innerHTML = '<p>No health checks in this report. Press “Refresh health”.</p>'
    return
  }
  const table = document.createElement('table')
  const head = document.createElement('tr')
  ;['Status', 'Check', 'Message', 'What to do'].forEach((h) => {
    const th = document.createElement('th')
    th.scope = 'col'
    th.textContent = h
    head.appendChild(th)
  })
  table.appendChild(head)
  for (const c of checks) {
    const tr = document.createElement('tr')
    const tdS = document.createElement('td')
    tdS.appendChild(badge(c.status))
    const tdL = document.createElement('td')
    tdL.textContent = c.label || c.id
    const tdM = document.createElement('td')
    tdM.textContent = c.message || ''
    const tdH = document.createElement('td')
    tdH.textContent = c.hint || '—'
    tdH.className = 'hint'
    tr.append(tdS, tdL, tdM, tdH)
    table.appendChild(tr)
  }
  box.appendChild(table)
}

function renderRuntimes (data) {
  const box = document.getElementById('runtime')
  box.innerHTML = ''
  const rt = data.runtimes || {}
  const setup = data.setup || {}
  const ul = document.createElement('ul')
  const add = (label, value, cls) => {
    const li = document.createElement('li')
    li.textContent = `${label}: `
    const strong = document.createElement('strong')
    strong.textContent = value
    if (cls) strong.className = cls
    li.appendChild(strong)
    ul.appendChild(li)
  }
  add('Runtime dir', rt.runtime_dir || 'unknown')
  add('Ready flag', rt.ready ? 'present — setup complete' : 'MISSING — setup incomplete', rt.ready ? 'ok' : 'err')
  const missing = rt.missing || []
  add('Missing runtimes', missing.length ? missing.join(', ') : 'none', missing.length ? 'warn' : 'ok')
  if (rt.manifest_error && !rt.manifest) {
    add('Manifest', rt.manifest_error, 'warn')
  } else if (rt.manifest) {
    add('Manifest', 'present', 'ok')
  }
  add('Configured (.env)', setup.configured ? `yes${setup.provider ? ` — ${setup.provider}` : ''}${setup.model ? ` / ${setup.model}` : ''}` : (setup.env_error || 'no'), setup.configured ? 'ok' : 'warn')
  if (data.data_dir_error) add('Data dir', data.data_dir_error, 'err')
  else add('Data dir', `${data.data_dir} (${data.data_dir_size_human || '?'})`)
  box.appendChild(ul)
  if (!rt.ready || missing.length) {
    const p = document.createElement('p')
    p.className = 'hint'
    p.textContent = 'Fix: run first-run setup from the launcher, then press “Refresh health”. Logs are preserved across retries.'
    box.appendChild(p)
  }
}

function renderVault (vault) {
  const box = document.getElementById('vault')
  box.innerHTML = ''
  if (!vault) { box.textContent = 'No vault data.'; return }
  if (vault.error) {
    const p = document.createElement('p')
    p.innerHTML = '<span class="badge error">ERROR</span> '
    p.append(document.createTextNode(vault.error))
    box.appendChild(p)
    const hint = document.createElement('p')
    hint.className = 'hint'
    hint.textContent = 'Check that the data directory exists and is readable.'
    box.appendChild(hint)
    return
  }
  const ul = document.createElement('ul')
  const add = (k, v, cls) => {
    const li = document.createElement('li')
    li.textContent = `${k}: `
    const s = document.createElement('strong')
    s.textContent = v
    if (cls) s.className = cls
    li.appendChild(s)
    ul.appendChild(li)
  }
  add('Encrypted', vault.encrypted ? 'yes (locked)' : 'no (unlocked)', vault.encrypted ? 'ok' : '')
  add('Encrypted files', String(vault.encrypted_files ?? '?'))
  add('Tracked files', String(vault.total_files ?? '?'))
  add('Size', vault.total_size_human || String(vault.vault_size ?? vault.total_size ?? '?'))
  if (vault.pending_recovery) add('Pending recovery', 'YES — interrupted operation', 'warn')
  box.appendChild(ul)
  const msg = document.createElement('p')
  msg.textContent = vault.message || ''
  box.appendChild(msg)
  if (vault.pending_recovery) {
    const hint = document.createElement('p')
    hint.className = 'hint'
    hint.textContent = 'Fix: run “python -m security recover <data-dir>” before the next lock/unlock.'
    box.appendChild(hint)
  }
}

function logSection (title, entry) {
  const wrap = document.createElement('div')
  const h = document.createElement('h3')
  h.textContent = title
  wrap.appendChild(h)
  if (!entry || !entry.exists) {
    const p = document.createElement('p')
    p.className = 'hint'
    p.textContent = (entry && entry.message) || 'Log not found. This is normal before the first run.'
    wrap.appendChild(p)
    return wrap
  }
  if (entry.error_lines && entry.error_lines.length) {
    const p = document.createElement('p')
    p.appendChild(badge('warn'))
    p.append(document.createTextNode(` ${entry.error_lines.length} error/warning line(s) in tail:`))
    wrap.appendChild(p)
    const pre = document.createElement('pre')
    pre.tabIndex = 0
    pre.textContent = entry.error_lines.join('\n')
    wrap.appendChild(pre)
  }
  const tail = document.createElement('h4')
  tail.textContent = `Tail (${entry.lines ? entry.lines.length : 0} lines${entry.truncated ? ', truncated' : ''}) — ${entry.path}`
  wrap.appendChild(tail)
  const pre = document.createElement('pre')
  pre.tabIndex = 0
  pre.textContent = (entry.lines && entry.lines.length) ? entry.lines.join('\n') : '(empty log file)'
  wrap.appendChild(pre)
  return wrap
}

function renderLogs (data) {
  const box = document.getElementById('logs')
  box.innerHTML = ''
  const detail = data.logs_detail || {}
  box.appendChild(logSection('Gateway log', detail.gateway || data.logs?.gateway_log))
  box.appendChild(logSection('Launch log', detail.launch || data.logs?.launch_log))
  const setupEntry = (detail.setup_unix && detail.setup_unix.exists) ? detail.setup_unix : detail.setup_windows
  box.appendChild(logSection('Setup log', setupEntry || data.logs?.setup_log))
}

function renderCharts (data) {
  const fallback = document.getElementById('storage-fallback')
  fallback.innerHTML = ''
  const dataDirBytes = data.data_dir_size_bytes || 0
  const vaultBytes = (data.vault && (data.vault.vault_size ?? data.vault.total_size)) || 0
  const logsBytes = (data.logs && data.logs.size_bytes) || 0

  // Always provide an accessible text fallback.
  const table = document.createElement('table')
  const head = document.createElement('tr')
  ;['Metric', 'Bytes', 'Human'].forEach((t) => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = t; head.appendChild(th) })
  table.appendChild(head)
  const human = (n) => {
    if (n == null) return '?'
    const units = ['B', 'KB', 'MB', 'GB']
    let v = n
    for (const u of units) { if (v < 1024) return `${v.toFixed(1)}${u}`; v /= 1024 }
    return `${v.toFixed(1)}TB`
  }
  ;[['Data dir', dataDirBytes], ['Vault files', vaultBytes], ['Logs', logsBytes]].forEach(([k, v]) => {
    const tr = document.createElement('tr')
    ;[k, String(v), human(v)].forEach((c) => { const td = document.createElement('td'); td.textContent = c; tr.appendChild(td) })
    table.appendChild(tr)
  })
  fallback.appendChild(table)

  if (typeof Chart === 'undefined') {
    const p = document.createElement('p')
    p.className = 'hint'
    p.textContent = 'Charts unavailable offline — the table above shows the same data.'
    fallback.appendChild(p)
    return
  }
  try {
    const diskCtx = document.getElementById('diskChart').getContext('2d')
    if (diskChart) diskChart.destroy()
    diskChart = new Chart(diskCtx, {
      type: 'doughnut',
      data: { labels: ['Vault files', 'Other data'], datasets: [{ data: [vaultBytes, Math.max(dataDirBytes - vaultBytes, 0)], backgroundColor: ['#0b5fff', '#9e9e9e'] }] },
      options: { responsive: true }
    })
    const logsCtx = document.getElementById('logsChart').getContext('2d')
    if (logsChart) logsChart.destroy()
    logsChart = new Chart(logsCtx, {
      type: 'bar',
      data: { labels: ['Gateway logs'], datasets: [{ label: 'Bytes', data: [logsBytes], backgroundColor: '#0b5fff' }] },
      options: { responsive: true, scales: { y: { beginAtZero: true } } }
    })
  } catch (e) {
    const p = document.createElement('p')
    p.className = 'hint'
    p.textContent = `Charts failed to render (${e.message}) — the table above shows the same data.`
    fallback.appendChild(p)
  }
}

async function loadReport () {
  setErrors('')
  setStatus('Loading health report…')
  try {
    const data = await window.api.getHealthReport()
    if (data.error) {
      setStatus('No report to show.')
      setErrors(`Error reading health report: ${data.error}`)
      document.getElementById('checks').innerHTML = `<p>${data.error}</p>`
      return
    }
    document.getElementById('generated').textContent = `Generated: ${data.timestamp || 'unknown'} — ${data.data_dir || ''}`
    renderChecks(data.health_checks)
    renderRuntimes(data)
    renderVault(data.vault)
    renderLogs(data)
    document.getElementById('envPre').textContent = JSON.stringify(data.env || {}, null, 2)
    renderCharts(data)
    const nErr = (data.health_checks || []).filter((c) => c.status === 'error').length
    const nWarn = (data.health_checks || []).filter((c) => c.status === 'warn').length
    setStatus(nErr ? `${nErr} error(s), ${nWarn} warning(s) — see actionable checks.` : nWarn ? `${nWarn} warning(s) — see actionable checks.` : 'All checks look good.')
  } catch (e) {
    setStatus('Failed to load report.')
    setErrors(`Failed to load report: ${e}`)
  }
}

document.getElementById('refresh').addEventListener('click', async () => {
  setStatus('Regenerating health report…')
  try {
    const res = await window.api.runDoctor()
    if (res.exporter_err) setErrors(`Exporter issue: ${res.exporter_err}`)
  } catch (e) {
    setErrors(`Refresh failed: ${e}`)
  }
  setTimeout(loadReport, 600)
})

document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r') { e.preventDefault(); document.getElementById('refresh').click() }
})

initTheme()
loadReport()
