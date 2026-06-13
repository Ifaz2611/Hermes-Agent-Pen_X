async function loadReport() {
  try {
    const data = await window.api.getHealthReport()

    const content = document.getElementById('content');
    content.innerHTML = '';

    if (data.error) {
      content.textContent = 'Error reading health report: ' + data.error
      return
    }

    const vaultCard = document.createElement('div');
    vaultCard.className = 'card';
    vaultCard.innerHTML = `<h3>Vault</h3><pre>${JSON.stringify(data.vault, null, 2)}</pre>`;
    content.appendChild(vaultCard);

    const dataCard = document.createElement('div');
    dataCard.className = 'card';
    dataCard.innerHTML = `<h3>Data Directory</h3><p>${data.data_dir} — ${data.data_dir_size_human || 'N/A'}</p>`;
    content.appendChild(dataCard);

    const logsCard = document.createElement('div');
    logsCard.className = 'card';
    logsCard.innerHTML = `<h3>Logs</h3><p>Size: ${data.logs.size_human || 'N/A'}</p><pre>${(data.logs.gateway_last_lines || []).slice(-20).join('\n')}</pre>`;
    content.appendChild(logsCard);

    const envCard = document.createElement('div');
    envCard.className = 'card';
    envCard.innerHTML = `<h3>Environment</h3><pre>${JSON.stringify(data.env, null, 2)}</pre>`;
    content.appendChild(envCard);

  } catch (e) {
    document.getElementById('content').textContent = 'Failed to load report: ' + e;
  }
}

loadReport();
