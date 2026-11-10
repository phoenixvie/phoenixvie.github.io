import {test} from 'node:test';
import assert from 'node:assert/strict';
import {encodePdf, pdfViewerHtml} from '../src/pdfViewer.ts';

test('native PDF bytes survive base64 transfer including padding boundaries', () => {
  for (const length of [0,1,2,3,4,255,1024,179118]) {
    const bytes=Uint8Array.from({length},(_,i)=>(i*37)%256);
    assert.equal(encodePdf(bytes),Buffer.from(bytes).toString('base64'));
  }
});
test('PDF viewer renders downloaded bytes without a privileged app bridge', () => {
  const html=pdfViewerHtml(encodePdf(new TextEncoder().encode('%PDF-1.7')));
  assert.match(html,/PDF geladen/);
  assert.match(html,/isEvalSupported:false/);
  assert.doesNotMatch(html,/ReactNativeWebView/);
});
