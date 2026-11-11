// Render the first forum card into static HTML so the initial layout is stable.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
const context={window:{},document:{addEventListener(){}},console};
context.window.escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
vm.createContext(context);
for(const file of ['portal-data.js','icons.js','showcase.js'])vm.runInContext(fs.readFileSync(path.join(root,'site/js',file),'utf8'),context);
const forum=context.window.PORTAL.archive.find(f=>f.current);
const html=context.window.renderPortalCurrentCard(forum).replace(/<img\b[^>]*>/g,tag=>{
  const src=/src="([^"]+)"/.exec(tag);if(!src||tag.includes(' width='))return tag;
  const file=path.join(root,'site',src[1]);if(!fs.existsSync(file))return tag;
  const bytes=fs.readFileSync(file);if(bytes.length<24||bytes.toString('ascii',1,4)!=='PNG')return tag;
  return tag.slice(0,-1)+` width="${bytes.readUInt32BE(16)}" height="${bytes.readUInt32BE(20)}" decoding="async">`;
});
const file=path.join(root,'site/index.html');let s=fs.readFileSync(file,'utf8');
const marker='<!-- current-forum:start -->';
if(s.includes(marker))s=s.replace(/<!-- current-forum:start -->[\s\S]*?<!-- current-forum:end -->/,`${marker}${html}<!-- current-forum:end -->`);
else s=s.replace(/(<div[^>]*data-current-forum[^>]*>)(\s*)(<\/div>)/,`$1${marker}${html}<!-- current-forum:end -->$3`);
if(!s.includes(marker))throw new Error('Current forum placeholder not found');
fs.writeFileSync(file,s);
console.log('Static first forum card rendered');
