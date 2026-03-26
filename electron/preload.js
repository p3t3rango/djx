const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('djx', {
  isElectron: true,
  platform: process.platform,
});
