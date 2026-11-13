export function encodePdf(bytes: Uint8Array): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let result = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const value = (bytes[i] << 16) | ((bytes[i + 1] || 0) << 8) | (bytes[i + 2] || 0);
    result += alphabet[(value >>> 18) & 63] + alphabet[(value >>> 12) & 63] +
      (i + 1 < bytes.length ? alphabet[(value >>> 6) & 63] : '=') +
      (i + 2 < bytes.length ? alphabet[value & 63] : '=');
  }
  return result;
}

// The original PDF is downloaded by native networking, avoiding browser CORS restrictions.
export function pdfViewerHtml(base64: string, language: 'de' | 'en' = 'de', texts: Record<string,string> = {}): string {
  const label=(de: string,en: string)=>texts[de]??(language==='de'?de:en);
  const copy={title:label('Menü-PDF','Menu PDF'),loading:label('PDF wird geladen …','Loading PDF …'),page:label('PDF-Seite','PDF page'),loaded:label('PDF geladen ·','PDF loaded ·'),singular:label('Seite','page'),plural:label('Seiten','pages'),error:label('PDF konnte nicht angezeigt werden.','The PDF could not be displayed.')};
  const safe=(value: unknown)=>JSON.stringify(value).replace(/</g,'\\u003c');
  const title=copy.title.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]!));
  return `<!doctype html><html lang="${language}"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>body{margin:0;background:#edf0f4;font:14px Arial;color:#556}#status{padding:12px;text-align:center}canvas{display:block;margin:0 auto 12px;background:white;max-width:100%}</style><div id="status" role="status"></div><main id="pages"></main><script type="module">
  const copy=${safe(copy)},status=document.getElementById('status');status.textContent=copy.loading;
  try {
    const pdfjs=await import('https://cdn.jsdelivr.net/npm/pdfjs-dist@5.7.284/legacy/build/pdf.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc='https://cdn.jsdelivr.net/npm/pdfjs-dist@5.7.284/legacy/build/pdf.worker.mjs';
    const bytes=Uint8Array.from(atob(${safe(base64)}),c=>c.charCodeAt(0));
    const pdf=await pdfjs.getDocument({data:bytes,isEvalSupported:false,isOffscreenCanvasSupported:false,isImageDecoderSupported:false,standardFontDataUrl:'https://cdn.jsdelivr.net/npm/pdfjs-dist@5.7.284/standard_fonts/'}).promise;
    for(let i=1;i<=pdf.numPages;i++){
      const page=await pdf.getPage(i),natural=page.getViewport({scale:1}),width=window.innerWidth,ratio=Math.max(2,window.devicePixelRatio||1);
      const viewport=page.getViewport({scale:width/natural.width*ratio}),canvas=document.createElement('canvas');
      canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);canvas.style.width=width+'px';canvas.style.height=viewport.height/ratio+'px';canvas.setAttribute('aria-label',copy.page+' '+i);
      document.getElementById('pages').appendChild(canvas);
      await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
    }
    status.textContent=copy.loaded+' '+pdf.numPages+' '+(pdf.numPages===1?copy.singular:copy.plural);
  } catch(error){status.textContent=copy.error+' '+error.message;}
  </script></html>`;
}
