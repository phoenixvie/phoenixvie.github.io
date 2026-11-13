export function webUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null;} catch {return null;}
}

export function isTrustedAppMessageSource(value: unknown, baseUrl: string): boolean {
  if (typeof value !== 'string') return false;
  // The main embedded WebView alone receives this handler; external pages use a separate WebView.
  if (value === 'about:blank') return true;
  try {
    const source = new URL(value), base = new URL(baseUrl);
    // Android WebMessageListener sends sourceOrigin, while the legacy bridge sends the full URL.
    return source.origin === base.origin && ['/', base.pathname, base.pathname + 'index.html'].includes(source.pathname);
  } catch {return false;}
}

type LinkHandlers = {
  openSource: (url: string, title: string) => void;
  openExternal: (url: string) => void;
  share: (text: string) => void;
  exit: () => void;
  usage?: (event: unknown, props: unknown) => void;
  setLanguage?: (language: 'de' | 'en', texts?: Record<string,string>, manual?: boolean) => void;
};

export function routeAppMessage(source: unknown, raw: unknown, baseUrl: string, handlers: LinkHandlers): void {
  if (!isTrustedAppMessageSource(source, baseUrl) || typeof raw !== 'string') return;
  let item;
  try {item = JSON.parse(raw);} catch {return;}
  if (!item || typeof item !== 'object') return;
  if (item.type === 'language-changed' && (item.language === 'de' || item.language === 'en')) {const texts=item.texts&&typeof item.texts==='object'&&!Array.isArray(item.texts)?Object.fromEntries(Object.entries(item.texts).filter(([key,value])=>key.length<=500&&typeof value==='string'&&value.length<=4000).slice(0,1000)):undefined;handlers.setLanguage?.(item.language,texts as Record<string,string>|undefined,item.manual===true);}
  else if (item.type === 'open-source' || item.type === 'open-external') {
    const url = webUrl(item.url);
    if (url) handlers.openSource(url, item.type === 'open-source' && typeof item.title === 'string' ? item.title : 'Restaurant');
    else if (item.type === 'open-external' && typeof item.url === 'string' && /^(mailto:|tel:)/i.test(item.url)) handlers.openExternal(item.url);
  } else if (item.type === 'share' && typeof item.text === 'string') handlers.share(item.text);
  else if (item.type === 'usage') handlers.usage?.(item.event,item.props);
  else if (item.type === 'exit') handlers.exit();
}
