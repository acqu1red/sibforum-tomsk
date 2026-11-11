const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const site=process.env.SITE_BUILD_DIR ? path.resolve(process.env.SITE_BUILD_DIR) : path.resolve(__dirname,'../../site');
function visit(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,e.name);if(e.isDirectory()){visit(file);continue;}if(!e.name.endsWith('.html'))continue;
 let s=fs.readFileSync(file,'utf8');s=s.replace(/\b(src|href)="([^"?#]+\.(?:css|js))(?:\?v=[a-f0-9]+)?"/g,(tag,attr,url)=>{if(/^https?:/.test(url))return tag;const target=url.startsWith('/')?path.join(site,url):path.resolve(path.dirname(file),url);if(!fs.existsSync(target))throw Error('Missing asset '+target);const hash=crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex').slice(0,12);return `${attr}="${url}?v=${hash}"`;});fs.writeFileSync(file,s);
}}
visit(site);console.log('Static CSS and JavaScript URLs versioned by content hash');
