import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Alert, AppState, BackHandler, Linking, Modal, Pressable, Share, StatusBar, StyleSheet, Text, View} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import {WebView, WebViewMessageEvent} from 'react-native-webview';
import {previewHtml} from './src/previewHtml';
import {encodePdf, pdfViewerHtml} from './src/pdfViewer';
import {routeAppMessage, webUrl} from './src/nativeLinks';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {languagePreferences} from './src/preferences';
import {usage} from './src/analytics';

const baseUrl = 'https://phoenixvie.github.io/wu-lunch-app/preview/';
const nativeLanguage = /^de(?:-|$)/i.test(Intl.DateTimeFormat().resolvedOptions().locale) ? 'de' : 'en';
const nativeText = (de: string, en: string, language = nativeLanguage) => language === 'de' ? de : en;
const preferences=languagePreferences(AsyncStorage);
const defaultHtmlSource = {html: previewHtml.replace('<head>',`<head><script>window.WU_SYSTEM_LANGUAGE='${nativeLanguage}';</script>`), baseUrl};
function openExternal(url: string, language = nativeLanguage, texts: Record<string,string> = {}) {
  if (/^(https?:|mailto:|tel:)/i.test(url)) Linking.openURL(url).catch(() => {
    Alert.alert(texts['Link konnte nicht geöffnet werden']??nativeText('Link konnte nicht geöffnet werden','Could not open link',language),texts['Bitte prüfe, ob eine passende App installiert ist.']??nativeText('Bitte prüfe, ob eine passende App installiert ist.','Please check that a suitable app is installed.',language));
  });
}
function AppContent() {
  const [language, setLanguage] = useState<'de' | 'en'>(nativeLanguage);
  const [texts,setTexts]=useState<Record<string,string>>({});
  const [htmlSource,setHtmlSource]=useState<typeof defaultHtmlSource|null>(null);
  const nativeText = (de: string, en: string) => texts[de]??(language === 'de' ? de : en);
  const openExternalLink = (url: string) => openExternal(url, language,texts);
  useEffect(()=>{let active=true;void preferences.load().then(saved=>{if(!active)return;if(saved)setLanguage(saved);setHtmlSource(saved?{html:previewHtml.replace('<head>',`<head><script>window.WU_SYSTEM_LANGUAGE='${nativeLanguage}';window.WU_SAVED_LANGUAGE='${saved}';</script>`),baseUrl}:defaultHtmlSource);});return()=>{active=false};},[]);
  const languageRef=useRef(language);languageRef.current=language;
  const main = useRef<WebView<{}>>(null);
  const browser = useRef<WebView<{}>>(null);
  const [page, setPage] = useState<{url: string; title: string; loading?: boolean; pdf?: string} | null>(null);
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
  useEffect(() => {
    if(!htmlSource)return;
    usage.state(AppState.currentState||'active',languageRef.current);
    const listener=AppState.addEventListener('change',state=>{
      usage.state(state,languageRef.current);
      if(state==='active')main.current?.injectJavaScript('window.wuFoodRefresh?.();true;');
    });
    return ()=>listener.remove();
  },[htmlSource]);
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
      openSource: (url, title) => {void openSource(url, title);}, openExternal: openExternalLink, setLanguage:(next,copy,manual)=>{setLanguage(next);languageRef.current=next;if(copy)setTexts(previous=>JSON.stringify(previous)===JSON.stringify(copy)?previous:copy);if(manual)void preferences.save(next).catch(()=>{});},
      share: text => {Share.share({message: text}).catch(() => {});},
      exit: () => BackHandler.exitApp(),
      usage:(event,props)=>usage.event(event,props),
    });
  };
  return <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
    <StatusBar barStyle="light-content" />
    {htmlSource ? <WebView<{}> ref={main} source={htmlSource} originWhitelist={['*']} onMessage={message}
      cacheEnabled={false}
      javaScriptEnabled domStorageEnabled setSupportMultipleWindows={false} style={styles.web}
      onShouldStartLoadWithRequest={request => {
        if (request.isTopFrame === false || request.url === 'about:blank' || request.url.split('?')[0] === baseUrl || request.url.split('?')[0] === baseUrl+'index.html') return true;
        const url=webUrl(request.url);
        if(url)void openSource(url,'Restaurant');else openExternalLink(request.url); return false;
      }} /> : <View style={[styles.web,{justifyContent:'center'}]}><ActivityIndicator color="#087cf4" /></View>}
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
        <View style={styles.browserFooter}><Pressable accessibilityLabel={nativeText('Zurück zum Menü','Back to menu')} onPress={closePage} style={styles.back}><Text style={styles.footerText}>{nativeText('Zurück','Back')}</Text></Pressable></View>
      </SafeAreaView>
    </Modal>
  </SafeAreaView>;
}
export default function App() {return <SafeAreaProvider><AppContent /></SafeAreaProvider>;}
const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: '#087cf4'}, web: {flex: 1, backgroundColor: '#fff'},
  browserFooter: {height: 60, alignItems:'center',justifyContent:'center',backgroundColor:'#087cf4',borderTopWidth:1,borderTopColor:'#087cf4'},
  footerText: {fontSize:16,color:'#fff'},
  back: {width: 65, height: 48, alignItems: 'center', justifyContent: 'center'}, backText: {fontSize: 12, color: '#fff'},
  title: {flex: 1, textAlign: 'center', color: '#fff', fontSize: 22, fontWeight: '500'},
  loader: {position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff'},
  failure: {padding: 18, gap: 12, alignItems: 'center', backgroundColor: '#fff'}, link: {color: '#087cf4'},
});
