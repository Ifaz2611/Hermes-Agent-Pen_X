let diskChart = null
let logsChart = null
let apiChart = null

async function renderCharts(data) {
  // Disk / Vault chart
  const diskCtx = document.getElementById('diskChart').getContext('2d')
  const dataDirBytes = data.data_dir_size_bytes || 0
  const vaultBytes = (data.vault && data.vault.vault_size) ? data.vault.vault_size : 0
  const freeBytes = Math.max(dataDirBytes - vaultBytes, 0)

  const diskDataset = {
    labels: ['Vault (enc files)', 'Other data'],
    datasets: [{
      data: [vaultBytes, Math.max(dataDirBytes - vaultBytes, 0)],
      backgroundColor: ['#ff6384', '#36a2eb']
    }]
  }

  if (diskChart) diskChart.destroy()
  diskChart = new Chart(diskCtx, { type: 'doughnut', data: diskDataset, options: {responsive:true} })

  // Logs chart (single value)
  const logsCtx = document.getElementById('logsChart').getContext('2d')
  const logsBytes = (data.logs && data.logs.size_bytes) ? data.logs.size_bytes : 0
  if (logsChart) logsChart.destroy()
  logsChart = new Chart(logsCtx, { type: 'bar', data: { labels: ['Gateway logs'], datasets:[{label:'Bytes', data:[logsBytes], backgroundColor:'#ffa500'}] }, options: {responsive:true, scales: {y:{beginAtZero:true}}} })

  // API costs chart
  const apiCtx = document.getElementById('apiChart').getContext('2d')
  if (data.api_costs && typeof data.api_costs === 'object') {
    const labels = Object.keys(data.api_costs)
    const values = labels.map(k => Number(data.api_costs[k]) || 0)
    if (apiChart) apiChart.destroy()
    apiChart = new Chart(apiCtx, { type: 'bar', data: { labels, datasets:[{label:'Cost', data: values, backgroundColor: '#4caf50'}] }, options: {responsive:true, scales:{y:{beginAtZero:true}}} })
  } else {
    if (apiChart) apiChart.destroy()
    // show placeholder
    apiChart = new Chart(apiCtx, { type: 'bar', data: { labels:['No data'], datasets:[{label:'Cost', data:[0], backgroundColor:'#ddd'}] }, options:{responsive:true} })
  }
}

async function loadReport() {
  try {
    const data = await window.api.getHealthReport()

    if (data.error) {
      document.getElementById('content').textContent = 'Error reading health report: ' + data.error
      return
    }

    // Update vault and env text
    document.getElementById('vaultPre').textContent = JSON.stringify(data.vault, null, 2)
    document.getElementById('envPre').textContent = JSON.stringify(data.env, null, 2)

    // Render charts
    renderCharts(data)

    // Show recent log lines under logs card as a small block
    // (append lines below the logs chart)
    const logsCard = document.getElementById('logsChart').parentElement
    let existing = document.getElementById('logLines')
    if (existing) existing.remove()
    const pre = document.createElement('pre')
    pre.id = 'logLines'
    pre.style.maxHeight = '120px'
    pre.style.overflow = 'auto'
    pre.textContent = (data.logs && data.logs.gateway_last_lines) ? data.logs.gateway_last_lines.slice(-50).join('\n') : 'No log lines available'
    logsCard.appendChild(pre)

  } catch (e) {
    document.getElementById('content').textContent = 'Failed to load report: ' + e
  }
}

document.getElementById('refresh').addEventListener('click', async () => {
  // Trigger exporter via run-doctor to refresh health.json, then reload
  await window.api.runDoctor()
  setTimeout(loadReport, 400) // small delay to allow exporter to write file
})

// initial load
loadReport()
