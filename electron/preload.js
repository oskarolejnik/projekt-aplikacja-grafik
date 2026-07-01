const { contextBridge } = require('electron')

// Bezpieczny, minimalny most. Aplikacja webowa komunikuje się z backendem przez HTTP,
// więc nie potrzebuje API Electrona — wystawiamy tylko znacznik, że działamy w desktopie.
contextBridge.exposeInMainWorld('grafikDesktop', {
  jest: true,
  platforma: process.platform,
})
