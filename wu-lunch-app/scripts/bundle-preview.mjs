import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

const root = resolve(import.meta.dirname, '..');
const read = async path => (await readFile(resolve(root, path), 'utf8')).replace(/\r\n/g, '\n');
const [template, css, js, font] = await Promise.all([read('preview/index.html'), read('preview/style.css'), read('preview/app.js'), read('assets/material-symbols-font.json')]);
const fontData = JSON.parse(font);
const hash = createHash('sha256').update(template + css + js).digest('hex');
const nativeCSS = `@font-face{font-family:'Material Symbols Outlined';font-style:normal;font-weight:400;src:url(data:${fontData.mime};base64,${fontData.base64}) format('${fontData.format}')}html,body{width:100%;height:100%;min-height:0;display:block;background:#fff}.app{width:100%;height:100dvh;min-height:0;border-radius:0;box-shadow:none;margin:0}.material-symbols-outlined{font-display:block}`;
const html = template
  .replace('<title>WU Food · App-Vorschau</title>', '<title>WU Food</title>')
  .replace(/<link[^>]+(?:fonts.googleapis.com|fonts.gstatic.com)[^>]*>\s*/g, '')
  .replace(/<link rel="stylesheet" href="\.\/style\.css(?:\?[^"<>]*)?">/, `<style>${css}\n${nativeCSS}</style>`)
  .replace(/<script defer src="\.\/app\.js(?:\?[^"<>]*)?"><\/script>/, `<script>window.WU_FOOD_BUILD='${hash}';document.addEventListener('DOMContentLoaded',()=>{\n${js.replace(/<\/script/gi, '<\\/script')}\n});</script>`);
await writeFile(resolve(root, 'src/previewHtml.ts'), `// Generated from preview sources; run npm run bundle:preview.\nexport const designHash = ${JSON.stringify(hash)};\nexport const previewHtml = ${JSON.stringify(html)};\n`);
console.log('Bundled current preview design: ' + hash);
