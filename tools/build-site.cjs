const fs=require('node:fs'),path=require('node:path');
const source=path.resolve(__dirname,'../site'),destination=path.resolve(process.argv[2]||'.deploy-site');
if(destination===source)throw Error('Build destination must differ from source');
const configFile=path.resolve(__dirname,'../deploy/public-assets.json');
const config=fs.existsSync(configFile)?JSON.parse(fs.readFileSync(configFile,'utf8')):{};
const base=(config.base_url||'').replace(/\/$/,'');
if(base&&!/^https:\/\/[^/]+\.storage\.yandexcloud\.net\/site$/.test(base))throw Error('Expected the project Object Storage asset base');
function asset(url,file){if(!base||/^(?:https?:|data:|#|mailto:)/.test(url))return url;const clean=url.split(/[?#]/)[0];const full=clean.startsWith('/')?path.join(source,clean):path.resolve(path.dirname(file),clean);const relative=path.relative(source,full).split(path.sep).join('/');return relative.startsWith('img/')?base+'/'+relative+url.slice(clean.length):url;}
function visit(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const input=path.join(dir,e.name),relative=path.relative(source,input),output=path.join(destination,relative);if(e.isDirectory()){if(base&&relative==='img')continue;visit(input);continue;}fs.mkdirSync(path.dirname(output),{recursive:true});if(/\.(?:html|css)$/.test(e.name)){let text=fs.readFileSync(input,'utf8');text=text.replace(/\b(src|href)="([^"\s]+)"/g,(match,attr,url)=>attr+'="'+asset(url,input)+'"');text=text.replace(/url\((['"]?)([^)'"\s]+)\1\)/g,(match,quote,url)=>'url('+quote+asset(url,input)+quote+')');if(e.name.endsWith('.html')&&base)text=text.replace('</head>','<script>window.PUBLIC_ASSET_BASE_URL='+JSON.stringify(base)+'</script>\n</head>');fs.writeFileSync(output,text);}else fs.copyFileSync(input,output);}}
visit(source);console.log('Built website:',destination,base?'Object Storage images; no local img directory':'local images');
