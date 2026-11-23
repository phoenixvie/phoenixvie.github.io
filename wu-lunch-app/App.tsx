import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Alert, AppState, BackHandler, Linking, Modal, Platform, Pressable, Settings, Share, StatusBar, StyleSheet, Text, View} from 'react-native';
import {SafeAreaProvider, SafeAreaView, useSafeAreaInsets} from 'react-native-safe-area-context';
import {WebView, WebViewMessageEvent} from 'react-native-webview';
import {designHash, previewHtml} from './src/previewHtml';
import {remoteUi, RemotePage} from './src/remoteUi';
import {encodePdf, pdfViewerHtml} from './src/pdfViewer';
import {routeAppMessage, webUrl} from './src/nativeLinks';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {AppLanguage, languagePreferences} from './src/preferences';
import {usage} from './src/analytics';
import appConfig from './app.json';

const baseUrl = 'https://phoenixvie.github.io/wu-lunch-app/preview/';
const nativeLanguage = /^de(?:-|$)/i.test(Intl.DateTimeFormat().resolvedOptions().locale) ? 'de' : 'en';
const nativeText = (de: string, en: string, language = nativeLanguage) => language === 'de' ? de : en;
const preferences=languagePreferences(AsyncStorage);
// Nur für App-Store-Screenshots: Die iOS-App kann per Startargument (-wuStartScreen map|meet|restaurant:<id>|info:<id>)
// direkt eine Ansicht öffnen. Nutzer können keine Startargumente setzen; unbekannte Werte werden ignoriert.
const startScreen = (() => {try {const value = Platform.OS === 'ios' ? String(Settings.get('wuStartScreen') ?? '') : ''; return /^(map|meet|(restaurant|info):[a-z0-9-]+)$/.test(value) ? value : '';} catch {return '';}})();
// Version und System für den Update-Hinweis (im Admin ausgelöst); der Store-Link steht fest in der App.
const appVersion = /^\d+\.\d+\.\d+$/.test(appConfig.expo.version) ? appConfig.expo.version : '0.0.0';
const storeUrl = Platform.OS === 'ios' ? 'https://apps.apple.com/app/id6836345799' : 'market://details?id=at.startit.wufood';
const openStore = () => {Linking.openURL(storeUrl).catch(() => {Linking.openURL('https://play.google.com/store/apps/details?id=at.startit.wufood').catch(() => {});});};
const headScript = (saved?: string) => `<head><script>window.WU_APP={version:'${appVersion}',platform:'${Platform.OS === 'ios' ? 'ios' : 'android'}'};window.WU_SYSTEM_LANGUAGE='${nativeLanguage}';${saved ? `window.WU_SAVED_LANGUAGE='${saved}';` : ''}${startScreen ? `window.WU_START_SCREEN='${startScreen}';` : ''}</script>`;
// Oberfläche: eingebaut (previewHtml) oder – wenn vorhanden und bewährt – die vom Server nachgeladene Fassung.
const pageSource = (html: string, saved?: AppLanguage | null) => ({html: html.replace('<head>', headScript(saved || undefined)), baseUrl});
const remote = remoteUi(AsyncStorage, appVersion, designHash);
const READY_TIMEOUT = 12000;
function openExternal(url: string, language = nativeLanguage, texts: Record<string,string> = {}) {
  if (/^(https?:|mailto:|tel:)/i.test(url)) Linking.openURL(url).catch(() => {
    Alert.alert(texts['Link konnte nicht geöffnet werden']??nativeText('Link konnte nicht geöffnet werden','Could not open link',language),texts['Bitte prüfe, ob eine passende App installiert ist.']??nativeText('Bitte prüfe, ob eine passende App installiert ist.','Please check that a suitable app is installed.',language));
  });
}
function AppContent() {
  const [language, setLanguage] = useState<'de' | 'en'>(nativeLanguage);
  const [texts,setTexts]=useState<Record<string,string>>({});
  const [htmlSource,setHtmlSource]=useState<{html: string; baseUrl: string}|null>(null);
  // Nachgeladene Oberfläche: shownHash = gerade gezeigte Fassung (null = eingebaute); awaiting = wartet noch auf die
  // Rückmeldung „ui-ready" der Seite. Bleibt sie aus oder meldet der WebView einen Fehler, gilt die Fassung als
  // unbrauchbar und die eingebaute wird gezeigt.
  const savedLanguage=useRef<AppLanguage|null>(null);
  const shownHash=useRef<string|null>(null);
  const awaiting=useRef<string|null>(null);
  const readyTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const leftAt=useRef(0);
  const showPage=(next: RemotePage|null)=>{
    if(readyTimer.current)clearTimeout(readyTimer.current);
    shownHash.current=next?.hash??null;awaiting.current=next?.hash??null;
    setHtmlSource(pageSource(next?next.html:previewHtml,savedLanguage.current));
    if(next)readyTimer.current=setTimeout(()=>failRemote(next.hash),READY_TIMEOUT);
  };
  const failRemote=(hash: string)=>{if(awaiting.current!==hash)return;awaiting.current=null;void remote.reject(hash);showPage(null);};
  const uiReady=(build: string)=>{if(awaiting.current!==build)return;awaiting.current=null;if(readyTimer.current)clearTimeout(readyTimer.current);void remote.confirm(build);};
  const nativeText = (de: string, en: string) => texts[de]??(language === 'de' ? de : en);
  const openExternalLink = (url: string) => openExternal(url, language,texts);
  useEffect(()=>{let active=true;void Promise.all([preferences.load(),remote.start()]).then(([saved,next])=>{if(!active)return;if(saved)setLanguage(saved);savedLanguage.current=saved;showPage(next);void remote.check();});return()=>{active=false;if(readyTimer.current)clearTimeout(readyTimer.current);};},[]);
  const languageRef=useRef(language);languageRef.current=language;
  // iPhone: Der Bereich unter der App (Home-Leiste) ist weiß wie die Liste und die Menüleiste, nicht blau wie die Kopfzeile.
  const insets=useSafeAreaInsets();const iosBottom=Platform.OS==='ios';
  const main = useRef<WebView<{}>>(null);
  const browser = useRef<WebView<{}>>(null);
  const [page, setPage] = useState<{url: string; title: string; loading?: boolean; pdf?: string} | null>(null);
  const pageRef=useRef(page);pageRef.current=page;
  const sourceRequest = useRef(0);
  const [canGoBack, setCanGoBack] = useState(false);
  const [failed, setFailed] = useState(false);
  const closePage = () => {sourceRequest.current++; setPage(null); setCanGoBack(false); setFailed(false);main.current?.injectJavaScript('window.wuFoodRefresh?.();true;');};
  const openSource = async (url: string, title: string) => {
    const request = ++sourceRequest.current;
    setFailed(false); setCanGoBack(false); setPage({url, title, loading:true});
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      // Some restaurant endpoints return HTML for HEAD but a PDF for GET.
      const response = await fetch(url, {signal:controller.signal, headers:{'Cache-Control':'no-cache'}});
      let pdf: string | undefined;
      if (response.ok && (response.headers.get('content-type') || '').includes('application/pdf')) {
        const bytes = new Uint8Array(await response.arrayBuffer());
        pdf = pdfViewerHtml(encodePdf(bytes),language,texts);
      }
      if (request === sourceRequest.current) setPage({url, title, pdf});
    } catch {
      if (request === sourceRequest.current) setPage({url, title});
    } finally {clearTimeout(timeout);}
  };
  const browserBack = () => {if (canGoBack) browser.current?.goBack(); else closePage();};
  const started=htmlSource!==null;
  useEffect(() => {
    if(!started)return;
    usage.state(AppState.currentState||'active',languageRef.current);
    const listener=AppState.addEventListener('change',state=>{
      usage.state(state,languageRef.current);
      if(state!=='active'){if(!leftAt.current)leftAt.current=Date.now();return;}
      main.current?.injectJavaScript('window.wuFoodRefresh?.();true;');
      // Zurück im Vordergrund: nach einer neuen Oberfläche sehen. War die App länger weg und ist keine Restaurantseite
      // offen, wird eine bereitliegende Fassung jetzt gezeigt (oder nach dem Abschalten im Admin wieder die eingebaute).
      const away=leftAt.current?Date.now()-leftAt.current:0;leftAt.current=0;
      void remote.check().then(()=>away>=30000&&!pageRef.current?remote.start():undefined).then(next=>{
        if(next===undefined||awaiting.current)return;
        if((next?.hash??null)!==shownHash.current)showPage(next);
      }).catch(()=>{});
    });
    return ()=>listener.remove();
  },[started]);
  useEffect(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (page) {if (canGoBack) browser.current?.goBack(); else closePage();}
      else main.current?.injectJavaScript('window.wuFoodBack?.();true;');
      return true;
    });
    return () => handler.remove();
  }, [page, canGoBack]);
  const message = ({nativeEvent}: WebViewMessageEvent) => {
    routeAppMessage(nativeEvent.url, nativeEvent.data, baseUrl, {
      openSource: (url, title) => {void openSource(url, title);}, openExternal: openExternalLink, setLanguage:(next,copy,manual)=>{setLanguage(next);languageRef.current=next;if(copy)setTexts(previous=>JSON.stringify(previous)===JSON.stringify(copy)?previous:copy);if(manual){savedLanguage.current=next;void preferences.save(next).catch(()=>{});}},
      share: text => {Share.share({message: text}).catch(() => {});},
      exit: () => BackHandler.exitApp(),
      openStore,
      uiReady,
      usage:(event,props)=>usage.event(event,props),
    });
  };
  return <SafeAreaView style={styles.screen} edges={iosBottom ? ['top'] : ['top', 'bottom']}>
    <StatusBar barStyle="light-content" />
    <View style={[styles.web, iosBottom ? {paddingBottom: insets.bottom} : null]}>
    {htmlSource ? <WebView<{}> ref={main} source={htmlSource} originWhitelist={['*']} onMessage={message}
      cacheEnabled={false}
      onError={()=>{if(awaiting.current)failRemote(awaiting.current);}}
      javaScriptEnabled domStorageEnabled setSupportMultipleWindows={false} style={styles.web}
      onShouldStartLoadWithRequest={request => {
        if (request.isTopFrame === false || request.url === 'about:blank' || request.url.split('?')[0] === baseUrl || request.url.split('?')[0] === baseUrl+'index.html') return true;
        const url=webUrl(request.url);
        if(url)void openSource(url,'Restaurant');else openExternalLink(request.url); return false;
      }} /> : <View style={[styles.web,{justifyContent:'center'}]}><ActivityIndicator color="#087cf4" /></View>}
    </View>
    <Modal visible={!!page} onRequestClose={browserBack} animationType="slide">
      <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
        <StatusBar barStyle="light-content" />
        {page?.loading ? <View style={[styles.web,{justifyContent:'center'}]}><ActivityIndicator color="#087cf4" /></View> : page ? <WebView<{}> ref={browser} source={page.pdf ? {html:page.pdf,baseUrl} : {uri: page.url}} style={styles.web} originWhitelist={['*']}
          startInLoadingState renderLoading={() => <View style={styles.loader}><ActivityIndicator color="#087cf4" /></View>}
          onNavigationStateChange={state => setCanGoBack(state.canGoBack)} onError={() => setFailed(true)}
          setSupportMultipleWindows={false} onShouldStartLoadWithRequest={request => {
            if (request.url === 'about:blank') return true;
            if (page.pdf && request.url.split('?')[0]===baseUrl) return true;
            if (webUrl(request.url)) {
              if(request.isTopFrame!==false && request.url!==page.url){void openSource(request.url,page.title);return false;}
              return true;
            }
            openExternalLink(request.url); return false;
          }} /> : null}
        {failed ? <View style={styles.failure}><Text>{nativeText('Die Restaurantseite konnte nicht geladen werden.','The restaurant website could not be loaded.')}</Text><Pressable onPress={() => {setFailed(false); browser.current?.reload();}}><Text style={styles.link}>{nativeText('Erneut versuchen','Try again')}</Text></Pressable></View> : null}
        <View style={styles.browserFooter}><Pressable accessibilityRole="button" accessibilityLabel={nativeText('Zurück zum Menü','Back to menu')} onPress={closePage} style={styles.back}><View style={styles.arrow}><View style={styles.arrowHead} /><View style={styles.arrowLine} /></View><Text style={styles.footerText} numberOfLines={1} maxFontSizeMultiplier={1.3}>{nativeText('Zurück','Back')}</Text></Pressable></View>
      </SafeAreaView>
    </Modal>
  </SafeAreaView>;
}
export default function App() {return <SafeAreaProvider><AppContent /></SafeAreaProvider>;}
const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: '#087cf4'}, web: {flex: 1, backgroundColor: '#fff'},
  browserFooter: {height: 60, alignItems:'center',justifyContent:'center',backgroundColor:'#087cf4',borderTopWidth:1,borderTopColor:'#087cf4'},
  footerText: {fontSize:16,color:'#fff'},
  // Pfeil und Wort stehen nebeneinander in einer Zeile. Vorher war der Knopf fest 65 breit: „←  Zurück“ brach um, der
  // Pfeil stand als eigenes Zeichen über dem Wort (Meldung des Betreibers, 22.11.2026). Der Pfeil ist jetzt gezeichnet.
  back: {height: 48, paddingHorizontal: 24, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10}, backText: {fontSize: 12, color: '#fff'},
  arrow: {width: 20, height: 20},
  arrowLine: {position: 'absolute', left: 2, right: 1, top: 9, height: 2, borderRadius: 1, backgroundColor: '#fff'},
  arrowHead: {position: 'absolute', left: 3, top: 5, width: 10, height: 10, borderLeftWidth: 2, borderBottomWidth: 2, borderColor: '#fff', transform: [{rotate: '45deg'}]},
  title: {flex: 1, textAlign: 'center', color: '#fff', fontSize: 22, fontWeight: '500'},
  loader: {position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff'},
  failure: {padding: 18, gap: 12, alignItems: 'center', backgroundColor: '#fff'}, link: {color: '#087cf4'},
});
