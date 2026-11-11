const fs=require('node:fs'),path=require('node:path');
const site=path.resolve(__dirname,'../../site');
fs.copyFileSync(path.join(site,'promtour/index.html'),path.join(site,'index.html'));
console.log('Main domain serves the current forum');
