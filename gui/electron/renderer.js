document.getElementById('launch').addEventListener('click', async () => {
  const res = await window.api.launchHermes()
  alert('Launch requested: ' + JSON.stringify(res))
})

document.getElementById('doctor').addEventListener('click', async () => {
  const res = await window.api.runDoctor()
  alert('Doctor requested: ' + JSON.stringify(res))
})

document.getElementById('data').addEventListener('click', async () => {
  const res = await window.api.openDataFolder()
  alert('Open data folder: ' + JSON.stringify(res))
})
