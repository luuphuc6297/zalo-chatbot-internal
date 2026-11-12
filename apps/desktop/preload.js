// Preload for the staff console. Runs sandboxed; exposes only getConfig/setConfig to the page.
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('thomhouse', {
  getConfig: () => ipcRenderer.invoke('thomhouse:config:get'),
  setConfig: (cfg) => ipcRenderer.invoke('thomhouse:config:set', cfg),
});
