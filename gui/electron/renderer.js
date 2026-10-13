const $ = (id) => document.getElementById(id)

function setStatus (msg) {
  $('status').textContent = msg
}

function setError (msg) {
  const box = $('errors')
  box.textContent = ''
  if (msg) {
    const p = document.createElement('p')
    p.className = 'err'
    p.textContent = msg
    box.appendChild(p)
  }
}

// ---- Theme (persisted, respects OS high-contrast preference) ----
function initTheme () {
  const btn = $('theme')
  const stored = (() => { try { return localStorage.getItem('hermes-theme') } catch { return null } })()
  const prefersHC = window.matchMedia && window.matchMedia('(prefers-contrast: more)').matches
  const startHC = stored === 'high-contrast' || (!stored && prefersHC)
  const apply = (hc) => {
    if (hc) document.body.setAttribute('data-theme', 'high-contrast')
    else document.body.removeAttribute('data-theme')
    btn.textContent = `High-contrast: ${hc ? 'on' : 'off'}`
    btn.setAttribute('aria-pressed', hc ? 'true' : 'false')
    try { localStorage.setItem('hermes-theme', hc ? 'high-contrast' : 'default') } catch { /* ignore */ }
  }
  apply(startHC)
  btn.addEventListener('click', () => {
    apply(document.body.getAttribute('data-theme') !== 'high-contrast')
    setStatus(`Theme: ${document.body.getAttribute('data-theme') === 'high-contrast' ? 'high-contrast on' : 'high-contrast off'}.`)
    btn.focus()
  })
}

// ---- Profiles ----
let pendingDelete = null

async function refreshProfiles () {
  const list = $('profile-list')
  const select = $('profile-select')
  try {
    const res = await window.api.listProfiles()
    if (!res.ok) {
      list.innerHTML = ''
      const li = document.createElement('li')
      li.innerHTML = '<span class="err">Cannot list profiles: </span>'
      li.append(document.createTextNode(res.error || 'unknown error'))
      list.appendChild(li)
      return
    }
    const current = select.value
    select.innerHTML = ''
    const def = document.createElement('option')
    def.value = ''
    def.textContent = 'Default (data/)'
    select.appendChild(def)
    for (const p of res.profiles) {
      const o = document.createElement('option')
      o.value = p.name
      o.textContent = p.name
      select.appendChild(o)
    }
    // Restore selection: prefer stored active, else keep current.
    const want = res.active || current
    if (want) select.value = want

    list.innerHTML = ''
    if (!res.profiles.length) {
      const li = document.createElement('li')
      li.textContent = 'No profiles yet. Create one above — the default data/ folder is used until then.'
      list.appendChild(li)
      return
    }
    for (const p of res.profiles) {
      const li = document.createElement('li')
      const name = document.createElement('strong')
      name.textContent = p.name
      li.appendChild(name)
      if (res.active === p.name) {
        const badge = document.createElement('span')
        badge.className = 'ok'
        badge.textContent = ' (active)'
        li.appendChild(badge)
      }
      li.appendChild(document.createTextNode(' '))
      const useBtn = document.createElement('button')
      useBtn.type = 'button'
      useBtn.textContent = res.active === p.name ? 'Active' : 'Switch to this profile'
      useBtn.disabled = res.active === p.name
      useBtn.setAttribute('aria-label', `Switch to profile ${p.name}`)
      useBtn.addEventListener('click', async () => {
        const r = await window.api.switchProfile(p.name)
        if (r.ok) { setStatus(`Active profile: ${p.name}.`); setError(''); await refreshProfiles() } else { setError(r.error || 'Switch failed.') }
      })
      const delBtn = document.createElement('button')
      delBtn.type = 'button'
      delBtn.textContent = 'Delete…'
      delBtn.setAttribute('aria-label', `Delete profile ${p.name}`)
      delBtn.addEventListener('click', () => openDeleteDialog(p.name))
      li.appendChild(useBtn)
      li.appendChild(document.createTextNode(' '))
      li.appendChild(delBtn)
      list.appendChild(li)
    }
  } catch (e) {
    setError(`Cannot list profiles: ${e}`)
  }
}

function openDeleteDialog (name) {
  pendingDelete = name
  $('delete-text').textContent = `“${name}” and its folder will be permanently removed. This cannot be undone.`
  $('delete-confirm-text').value = ''
  $('delete-confirm-check').checked = false
  $('delete-error').textContent = ''
  const dlg = $('delete-dialog')
  if (typeof dlg.showModal === 'function') dlg.showModal()
  $('delete-confirm-text').focus()
}

function closeDeleteDialog () {
  const dlg = $('delete-dialog')
  if (typeof dlg.close === 'function' && dlg.open) dlg.close()
  pendingDelete = null
}

// ---- Setup progress ----
async function refreshSetup () {
  const box = $('setup-state')
  try {
    const res = await window.api.getSetupProgress()
    if (!res.ok) { box.innerHTML = `<p class="err">Cannot read setup state: ${res.error}</p>`; return }
    const parts = []
    parts.push(`<p>Runtime dir: <code>${res.runtimeDir}</code></p>`)
    if (res.ready) parts.push('<p class="ok">Setup complete (ready.flag present).</p>')
    else parts.push('<p class="warn">Setup incomplete (ready.flag missing).</p>')
    if (res.cancelled) parts.push('<p class="warn">Last setup run was cancelled. Logs are preserved — run setup again to resume. This state is recoverable.</p>')
    if (res.running) parts.push('<p>Setup is currently running. Use “Cancel setup” to stop it safely.</p>')
    if (res.progress && !res.progress.error) {
      const p = res.progress
      parts.push(`<p>Stage: <strong>${p.stage || 'unknown'}</strong> (${p.percent != null ? `${p.percent}%` : 'no percent'}) — ${p.message || ''}</p>`)
      if (Array.isArray(p.stages)) {
        parts.push('<ul>' + p.stages.map((s) => `<li>${s.done ? '✓' : '○'} ${s.name} — ${s.status || ''}</li>`).join('') + '</ul>')
      }
    } else if (res.progress && res.progress.error) {
      parts.push(`<p class="warn">${res.progress.error}</p>`)
    }
    box.innerHTML = parts.join('')
    const logLines = (res.log && res.log.lines) ? res.log.lines.join('\n') : (res.log.message || 'No log available.')
    $('setup-log').textContent = logLines
  } catch (e) {
    box.innerHTML = `<p class="err">Cannot read setup state: ${e}</p>`
  }
}

function init () {
  initTheme()

  $('launch').addEventListener('click', async () => {
    setError('')
    const profile = $('profile-select').value
    setStatus(profile ? `Launching Hermes with profile “${profile}”…` : 'Launching Hermes…')
    const res = await window.api.launchHermes({ profile })
    if (res.status === 'started') setStatus(`Launch requested${res.profile ? ` (profile “${res.profile}”)` : ''}.`)
    else setError(res.error || 'Launch failed.')
  })

  $('doctor').addEventListener('click', async () => {
    setError('')
    setStatus('Generating health report…')
    const res = await window.api.runDoctor()
    if (res.status === 'dashboard-opened') setStatus('Health dashboard opened.')
    else if (res.status === 'dashboard-opened-with-errors') setError(`Dashboard opened, but the exporter failed: ${res.exporter_err}`)
    else setError(res.error || 'Health dashboard failed.')
  })

  $('data').addEventListener('click', async () => {
    const res = await window.api.openDataFolder()
    if (res.status === 'opened') setStatus('Data folder opened.')
    else setError(res.error || 'Cannot open data folder.')
  })

  $('profile-select').addEventListener('change', async (e) => {
    const r = await window.api.switchProfile(e.target.value)
    if (r.ok) { setStatus(e.target.value ? `Active profile: ${e.target.value}.` : 'Using default data/ folder.'); setError(''); await refreshProfiles() } else { setError(r.error || 'Switch failed.') }
  })

  $('create-profile').addEventListener('click', async () => {
    setError('')
    const input = $('new-profile')
    const name = input.value.trim()
    if (!name) { setError('Enter a profile name first.'); input.focus(); return }
    const res = await window.api.createProfile(name)
    if (res.ok) { setStatus(`Profile “${name}” created.`); input.value = ''; await refreshProfiles() } else { setError(res.error || 'Create failed.') }
  })
  $('new-profile').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); $('create-profile').click() }
  })

  $('delete-confirm').addEventListener('click', async () => {
    const typed = $('delete-confirm-text').value.trim()
    const checked = $('delete-confirm-check').checked
    if (!pendingDelete) return
    if (!checked) { $('delete-error').textContent = 'Check the acknowledgement box to confirm.'; return }
    if (typed !== pendingDelete) { $('delete-error').textContent = `Type “${pendingDelete}” exactly to confirm.`; $('delete-confirm-text').focus(); return }
    const res = await window.api.deleteProfile({ name: pendingDelete, confirmed: true, typedName: typed })
    if (res.ok) { closeDeleteDialog(); setStatus(`Profile “${pendingDelete}” deleted.`); setError(''); await refreshProfiles() }
    else { $('delete-error').textContent = res.error || 'Delete failed.' }
  })
  $('delete-abort').addEventListener('click', closeDeleteDialog)
  $('delete-dialog').addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); closeDeleteDialog() }
  })

  $('setup-refresh').addEventListener('click', refreshSetup)
  $('setup-run').addEventListener('click', async () => {
    const res = await window.api.runSetup()
    if (res.ok) setStatus(res.message || 'Setup started.')
    else setError(res.error || 'Cannot start setup.')
    await refreshSetup()
  })
  $('setup-cancel').addEventListener('click', async () => {
    const res = await window.api.cancelSetup()
    if (res.ok) setStatus(res.message || 'Cancellation requested.')
    else setError(res.error || 'Nothing to cancel.')
    await refreshSetup()
  })

  document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd+R refreshes setup state; Alt+1..3 jumps to main actions.
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r') { e.preventDefault(); refreshSetup() }
  })

  refreshProfiles()
  refreshSetup()
  setInterval(refreshSetup, 8000)
}

document.addEventListener('DOMContentLoaded', init)
