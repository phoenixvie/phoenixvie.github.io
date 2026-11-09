import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, BackHandler, Linking, Modal, Pressable, Share, StatusBar, StyleSheet, Text, View} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import {WebView, WebViewMessageEvent} from 'react-native-webview';
import {previewHtml} from './src/previewHtml';

const baseUrl = 'https://phoenixvie.github.io/wu-lunch-app/preview/';
const htmlSource = {html: previewHtml, baseUrl};
const webUrl = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  try {const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null;} catch {return null;}
};
function openExternal(url: string) {
  if (/^(https?:|mailto:|tel:)/i.test(url)) Linking.openURL(url).catch(() => {});
}
function AppContent() {
  const main = useRef<WebView<{}>>(null);
  const browser = useRef<WebView<{}>>(null);
  const [page, setPage] = useState<{url: string; title: string} | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [failed, setFailed] = useState(false);
  const closePage = () => {setPage(null); setCanGoBack(false); setFailed(false);};
  const browserBack = () => {if (canGoBack) browser.current?.goBack(); else closePage();};
  useEffect(() => {
    const handler = BackHandler.addEventListener('hardwareBackPress', () => {
      if (page) {if (canGoBack) browser.current?.goBack(); else closePage();}
      else main.current?.injectJavaScript('window.wuFoodBack?.();true;');
      return true;
    });
    return () => handler.remove();
  }, [page, canGoBack]);
  const message = ({nativeEvent}: WebViewMessageEvent) => {
    // Restaurant pages never receive this privileged bridge.
    try {
      const item = JSON.parse(nativeEvent.data);
      if (item.type === 'open-source') {
        const url = webUrl(item.url);
        if (url) {setFailed(false); setCanGoBack(false); setPage({url, title: typeof item.title === 'string' ? item.title : 'Restaurant'});}
      } else if (item.type === 'open-external' && typeof item.url === 'string') openExternal(item.url);
      else if (item.type === 'share' && typeof item.text === 'string') Share.share({message: item.text}).catch(() => {});
      else if (item.type === 'exit') BackHandler.exitApp();
    } catch { /* Ignore invalid messages. */ }
  };
  return <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
    <StatusBar barStyle="light-content" />
    <WebView<{}> ref={main} source={htmlSource} originWhitelist={['*']} onMessage={message}
      javaScriptEnabled domStorageEnabled setSupportMultipleWindows={false} style={styles.web}
      onShouldStartLoadWithRequest={request => {
        if (request.isTopFrame === false || request.url === 'about:blank' || request.url === baseUrl) return true;
        openExternal(request.url); return false;
      }} />
    <Modal visible={!!page} onRequestClose={browserBack} animationType="slide">
      <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
        <StatusBar barStyle="light-content" />
        <View style={styles.browserHeader}>
          <Pressable accessibilityLabel="Zurück zum Menü" onPress={browserBack} style={styles.back}><Text style={styles.backText}>Zurück</Text></Pressable>
          <Text style={styles.title} numberOfLines={1}>{page?.title}</Text>
          <Pressable accessibilityLabel="Restaurantseite schließen" onPress={closePage} style={styles.back}><Text style={styles.backText}>Schließen</Text></Pressable>
        </View>
        {page ? <WebView<{}> ref={browser} source={{uri: page.url}} style={styles.web} originWhitelist={['http://*', 'https://*']}
          startInLoadingState renderLoading={() => <View style={styles.loader}><ActivityIndicator color="#087cf4" /></View>}
          onNavigationStateChange={state => setCanGoBack(state.canGoBack)} onError={() => setFailed(true)}
          setSupportMultipleWindows={false} onShouldStartLoadWithRequest={request => {
            if (webUrl(request.url) || request.url === 'about:blank') return true;
            openExternal(request.url); return false;
          }} /> : null}
        {failed ? <View style={styles.failure}><Text>Die Restaurantseite konnte nicht geladen werden.</Text><Pressable onPress={() => {setFailed(false); browser.current?.reload();}}><Text style={styles.link}>Erneut versuchen</Text></Pressable></View> : null}
      </SafeAreaView>
    </Modal>
  </SafeAreaView>;
}
export default function App() {return <SafeAreaProvider><AppContent /></SafeAreaProvider>;}
const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: '#087cf4'}, web: {flex: 1, backgroundColor: '#fff'},
  browserHeader: {height: 78, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, backgroundColor: '#087cf4'},
  back: {width: 65, height: 48, alignItems: 'center', justifyContent: 'center'}, backText: {fontSize: 12, color: '#fff'},
  title: {flex: 1, textAlign: 'center', color: '#fff', fontSize: 22, fontWeight: '500'},
  loader: {position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff'},
  failure: {padding: 18, gap: 12, alignItems: 'center', backgroundColor: '#fff'}, link: {color: '#087cf4'},
});
