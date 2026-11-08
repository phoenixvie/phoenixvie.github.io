import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator, AppState, Image, Linking, Pressable, ScrollView,
  StatusBar, StyleSheet, Text, View,
} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import {Camera, Map, Marker} from '@maplibre/maplibre-react-native';
import {DisplayDish, LunchData, Restaurant, datesOfWeek, displayDate, displayPrice, initialDay, loadLunchData, visibleDishes} from './src/data';

const blue = '#087cf4';
const lightBlue = '#eef6ff';
const teamEmail = 'campusmenue@gmail.com';
const mapStyle = 'https://tiles.openfreemap.org/styles/liberty';
const fallbackLocations: Record<string, {latitude: number; longitude: number; address: string}> = {
  mensa: {latitude: 48.2129611, longitude: 16.4098281, address: 'Welthandelsplatz 1, 1020 Wien'},
  campus: {latitude: 48.21213, longitude: 16.41021, address: 'Welthandelsplatz 1, 1020 Wien'},
  baschly: {latitude: 48.21445, longitude: 16.40743, address: 'Welthandelsplatz 1, 1020 Wien'},
  glashaus: {latitude: 48.2118847, longitude: 16.4120651, address: 'Am Grünen Prater 11, 1020 Wien'},
  losteria: {latitude: 48.21468, longitude: 16.4052, address: 'Freudplatz 2, 1020 Wien'},
  gruenehuette: {latitude: 48.21758, longitude: 16.40406, address: 'Prater 196, 1020 Wien'},
  lia: {latitude: 48.2138325, longitude: 16.4082722, address: 'Welthandelsplatz 1, 1020 Wien'},
  topfdeckel: {latitude: 48.2128709, longitude: 16.4156227, address: 'Vorgartenstraße 206B, 1020 Wien'},
  omakueche: {latitude: 48.2130071, longitude: 16.4155067, address: 'Vorgartenstraße 206B, 1020 Wien'},
  karmafood: {latitude: 48.2182830, longitude: 16.4078761, address: 'Ausstellungsstraße 63, 1020 Wien'},
};
const knownLogos: Record<string, string> = {
  mensa: 'https://www.wu.ac.at/fileadmin/wu/h/campus/infrastructure/catering/Logo_Mensa.jpg',
  campus: 'https://www.wu.ac.at/fileadmin/wu/h/campus/infrastructure/catering/Logo_Das_Campus.jpg',
  baschly: 'https://www.wu.ac.at/fileadmin/wu/h/campus/infrastructure/catering/Baschly.jpg',
  losteria: 'https://www.wu.ac.at/fileadmin/wu/h/campus/infrastructure/catering/Logo_Losteria.jpg',
};

function Logo({restaurant}: {restaurant: Restaurant}) {
  const [failed, setFailed] = useState(false);
  const uri = restaurant.logoUrl || knownLogos[restaurant.id];
  if (uri && !failed) return <Image source={{uri}} style={styles.logo} onError={() => setFailed(true)} />;
  return <View style={styles.monogram}><Text style={styles.monogramText}>{restaurant.monogram || restaurant.name[0]}</Text></View>;
}

function SmallButton({label, onPress}: {label: string; onPress: () => void}) {
  return <Pressable onPress={onPress} style={styles.actionButton}><Text style={styles.actionText}>{label}</Text></Pressable>;
}

function openUrl(url: string) {
  Linking.openURL(url).catch(() => {});
}

function RestaurantMap({restaurants, onSelect, focused}: {restaurants: Restaurant[]; onSelect: (id: string) => void; focused?: Restaurant}) {
  const markers = restaurants.map(restaurant => {
    const fallback = fallbackLocations[restaurant.id];
    const latitude = restaurant.latitude ?? fallback?.latitude;
    const longitude = restaurant.longitude ?? fallback?.longitude;
    return latitude != null && longitude != null ? {restaurant, latitude, longitude} : null;
  }).filter((item): item is {restaurant: Restaurant; latitude: number; longitude: number} => item !== null);
  const latitude = focused?.latitude ?? (focused && fallbackLocations[focused.id]?.latitude) ?? 48.2133;
  const longitude = focused?.longitude ?? (focused && fallbackLocations[focused.id]?.longitude) ?? 16.409;
  return <View style={styles.mapWrap}>
    <Map mapStyle={mapStyle} style={StyleSheet.absoluteFill}>
      <Camera initialViewState={{center: [longitude, latitude], zoom: focused ? 16 : 14.5}} />
      {markers.map(({restaurant, latitude: lat, longitude: lon}) =>
        <Marker key={restaurant.id} id={restaurant.id} lngLat={[lon, lat]} onPress={() => onSelect(restaurant.id)}>
          <View style={styles.pin}><Text style={styles.pinText}>{restaurant.name.slice(0, 1).toUpperCase()}</Text></View>
        </Marker>
      )}
    </Map>
    {markers.length < restaurants.length ? <View style={styles.mapNotice}><Text style={styles.mapNoticeText}>{focused ? 'Dieser Standort ist noch nicht genau verortet.' : 'Weitere Standorte erscheinen, sobald ihre Koordinaten im Adminbereich ergänzt sind.'}</Text></View> : null}
    <View style={styles.mapAttribution}><Text style={styles.mapAttributionText}>© OpenStreetMap · OpenFreeMap</Text></View>
  </View>;
}

function DishCard({dish}: {dish: DisplayDish}) {
  return <View style={styles.dishCard}>
    <View style={styles.dishTop}><Text style={styles.dishName}>{dish.name}</Text><Text style={styles.price}>{dish.priceLabel || displayPrice(dish.price)}</Text></View>
    {dish.category ? <Text style={styles.category}>{dish.category}</Text> : null}
    {dish.description ? <Text style={styles.dishDescription}>{dish.description}</Text> : null}
    {dish.included_soup ? <Text style={styles.included}>Suppe: {dish.included_soup}</Text> : null}
    {dish.included_choices?.length ? <Text style={styles.included}>{dish.included_choices.join(' · ')}</Text> : null}
    {dish.allergens?.length ? <Text style={styles.allergens}>Allergene: {dish.allergens.join(', ')}</Text> : null}
  </View>;
}

function AppContent() {
  const [data, setData] = useState<LunchData | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [homeTab, setHomeTab] = useState<'list' | 'map'>('list');
  const [detailTab, setDetailTab] = useState<'menu' | 'map' | 'contact'>('menu');
  const [day, setDay] = useState('');
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const touchStart = useRef<number | null>(null);

  const refresh = useCallback(async (first = false) => {
    if (!first) setRefreshing(true);
    try {
      const loaded = await loadLunchData();
      setData(loaded);
      setDay(previous => datesOfWeek(loaded.weekStart).includes(previous) ? previous : initialDay(loaded));
      setError('');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Laden fehlgeschlagen.');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh(true);
    const timer = setInterval(() => refresh(), 15000);
    const listener = AppState.addEventListener('change', state => {if (state === 'active') refresh();});
    return () => {clearInterval(timer); listener.remove();};
  }, [refresh]);

  const restaurant = data?.restaurants.find(item => item.id === selectedId) || null;
  const days = data ? datesOfWeek(data.weekStart) : [];
  const changeDay = (step: number) => {
    const next = days.indexOf(day) + step;
    if (next >= 0 && next < days.length) setDay(days[next]);
  };
  const onTouchEnd = (endX: number) => {
    if (touchStart.current != null) {
      const delta = endX - touchStart.current;
      if (Math.abs(delta) > 70) changeDay(delta < 0 ? 1 : -1);
    }
    touchStart.current = null;
  };
  const selectRestaurant = (id: string) => {setSelectedId(id); setDetailTab('menu');};

  return <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
    <StatusBar barStyle="light-content" />
    <View style={styles.header}>
      {restaurant ? <Pressable onPress={() => setSelectedId(null)} accessibilityLabel="Zurück zur Restaurantliste" style={styles.back}><Text style={styles.backText}>‹</Text></Pressable> : null}
      <Text style={styles.headerTitle}>{restaurant?.name || 'WU Lunch'}</Text>
      <Pressable onPress={() => refresh()} accessibilityLabel="Daten aktualisieren" style={styles.refresh}><Text style={styles.refreshText}>{refreshing ? '…' : '⟳'}</Text></Pressable>
    </View>
    <View style={styles.body}>{!data ? <View style={styles.loading}><ActivityIndicator size="large" color={blue}/><Text style={styles.loadingText}>{error || 'Menüs werden geladen …'}</Text>{error ? <SmallButton label="Erneut versuchen" onPress={() => refresh(true)}/> : null}</View> :
      restaurant ? <>
        {detailTab === 'menu' ? <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.dayBar} contentContainerStyle={styles.dayBarContent}>
            {days.map(date => <Pressable key={date} onPress={() => setDay(date)} style={[styles.dayTab, day === date && styles.dayTabActive]}><Text style={[styles.dayTabText, day === date && styles.dayTabTextActive]}>{displayDate(date, {weekday: 'short', day: '2-digit', month: '2-digit'})}</Text></Pressable>)}
          </ScrollView>
          <ScrollView style={styles.content} contentContainerStyle={styles.menuContent} onTouchStart={event => {touchStart.current = event.nativeEvent.pageX;}} onTouchEnd={event => onTouchEnd(event.nativeEvent.pageX)}>
            <Text style={styles.dayHeading}>{displayDate(day).toUpperCase()}</Text>
            {visibleDishes(restaurant, day).length ? visibleDishes(restaurant, day).map((dish, index) => <DishCard dish={dish} key={index + '-' + dish.name}/>) : <View style={styles.empty}><Text style={styles.emptyTitle}>Noch nicht veröffentlicht</Text><Text style={styles.emptyText}>Das Menü erscheint, sobald das Restaurant es veröffentlicht.</Text></View>}
            <Text style={styles.sourceHint}>Angaben ohne Gewähr. Bitte das Menü auf der Restaurantwebseite prüfen.</Text>
          </ScrollView>
        </> : detailTab === 'map' ? <RestaurantMap restaurants={[restaurant]} focused={restaurant} onSelect={() => {}}/> :
          <ScrollView style={styles.content} contentContainerStyle={styles.contactContent}>
            <Text style={styles.contactHeading}>Restaurant kontaktieren</Text>
            {restaurant.phone ? <SmallButton label="☎  Anrufen" onPress={() => openUrl('tel:' + restaurant.phone)}/> : null}
            {restaurant.email ? <SmallButton label="✉  E-Mail" onPress={() => openUrl('mailto:' + restaurant.email)}/> : null}
            {restaurant.url ? <SmallButton label="↗  Webseite" onPress={() => openUrl(restaurant.url!)}/> : null}
            {(restaurant.address || fallbackLocations[restaurant.id]?.address) ? <><Text style={styles.contactHeading}>Standort</Text><Text style={styles.address}>{restaurant.address || fallbackLocations[restaurant.id]?.address}</Text><SmallButton label="⌖  Karte öffnen" onPress={() => setDetailTab('map')}/></> : null}
            <Text style={styles.contactHeading}>App-Team</Text><SmallButton label="✉  E-Mail" onPress={() => openUrl('mailto:' + teamEmail)}/>
            <SmallButton label="↗  Menü teilen" onPress={() => openUrl('https://phoenixvie.github.io/wu-lunch/')}/>
          </ScrollView>
        }
        <View style={styles.bottomTabs}>
          {([['menu', 'Menü', '♨'], ['map', 'Karte', '⌖'], ['contact', 'Kontakt', '☎']] as const).map(([tab, label, icon]) => <Pressable key={tab} style={styles.bottomTab} onPress={() => setDetailTab(tab)}><Text style={[styles.bottomIcon, detailTab === tab && styles.bottomActive]}>{icon}</Text><Text style={[styles.bottomLabel, detailTab === tab && styles.bottomActive]}>{label}</Text></Pressable>)}
        </View>
      </> : <>
        <View style={styles.segment}><Pressable onPress={() => setHomeTab('list')} style={[styles.segmentButton, homeTab === 'list' && styles.segmentSelected]}><Text style={[styles.segmentText, homeTab === 'list' && styles.segmentTextSelected]}>Liste</Text></Pressable><Pressable onPress={() => setHomeTab('map')} style={[styles.segmentButton, homeTab === 'map' && styles.segmentSelected]}><Text style={[styles.segmentText, homeTab === 'map' && styles.segmentTextSelected]}>Karte</Text></Pressable></View>
        {homeTab === 'list' ? <ScrollView style={styles.content}><Text style={styles.groupTitle}>WU Food · {displayDate(data.weekStart, {day: '2-digit', month: '2-digit'})}–{displayDate(data.weekEnd, {day: '2-digit', month: '2-digit'})}</Text>{data.restaurants.map(item => <Pressable key={item.id} style={styles.restaurantRow} onPress={() => selectRestaurant(item.id)}><Logo restaurant={item}/><View style={styles.restaurantMeta}><Text style={styles.restaurantName}>{item.name}</Text><Text style={styles.restaurantType}>{item.restaurantType || 'Restaurant'}</Text></View><Text style={styles.chevron}>›</Text></Pressable>)}{error ? <Text style={styles.error}>{error}</Text> : null}</ScrollView> : <RestaurantMap restaurants={data.restaurants} onSelect={selectRestaurant}/>}
      </>}</View>
    {data && error ? <Text style={styles.errorStrip}>{error}</Text> : null}
  </SafeAreaView>;
}

export default function App() {return <SafeAreaProvider><AppContent/></SafeAreaProvider>;}

const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: blue}, body: {flex: 1, backgroundColor: '#fff'},
  header: {backgroundColor: blue, height: 68, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18},
  headerTitle: {color: '#fff', fontSize: 23, fontWeight: '600', textAlign: 'center', flex: 1},
  back: {width: 38, alignItems: 'flex-start'}, backText: {color: '#fff', fontSize: 39, lineHeight: 44},
  refresh: {width: 38, alignItems: 'flex-end'}, refreshText: {color: '#fff', fontSize: 30},
  loading: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: 18, padding: 24}, loadingText: {fontSize: 16, color: '#526070', textAlign: 'center'},
  segment: {flexDirection: 'row', backgroundColor: blue, paddingHorizontal: 32, paddingBottom: 14},
  segmentButton: {flex: 1, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: '#fff'},
  segmentSelected: {backgroundColor: '#fff'}, segmentText: {color: '#fff', fontSize: 16, fontWeight: '600'}, segmentTextSelected: {color: blue},
  content: {flex: 1}, groupTitle: {backgroundColor: '#f5f6f8', color: '#536174', paddingHorizontal: 18, paddingVertical: 10, fontSize: 15},
  restaurantRow: {flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, minHeight: 82, borderBottomWidth: 1, borderBottomColor: '#e6e8ec'},
  logo: {width: 55, height: 55, borderRadius: 5, resizeMode: 'contain', backgroundColor: '#fff'},
  monogram: {width: 55, height: 55, borderRadius: 5, backgroundColor: lightBlue, alignItems: 'center', justifyContent: 'center'},
  monogramText: {color: blue, fontSize: 24, fontWeight: '700'}, restaurantMeta: {flex: 1, marginLeft: 15},
  restaurantName: {fontSize: 17, color: '#1b2938', fontWeight: '600'}, restaurantType: {fontSize: 14, color: '#728092', marginTop: 4},
  chevron: {fontSize: 32, color: '#b5bcc4', marginLeft: 8},
  dayBar: {flexGrow: 0, maxHeight: 58, borderBottomWidth: 1, borderColor: '#e5eaf1'}, dayBarContent: {paddingHorizontal: 8, alignItems: 'stretch'},
  dayTab: {paddingHorizontal: 13, paddingVertical: 17}, dayTabActive: {borderBottomWidth: 3, borderBottomColor: blue}, dayTabText: {color: '#667383', fontSize: 14}, dayTabTextActive: {color: blue, fontWeight: '700'},
  menuContent: {padding: 18, paddingBottom: 50}, dayHeading: {fontSize: 15, fontWeight: '700', color: '#526070', marginBottom: 13},
  dishCard: {padding: 15, marginBottom: 11, borderWidth: 1, borderColor: '#e5eaf0', borderRadius: 9, backgroundColor: '#fff'},
  dishTop: {flexDirection: 'row', alignItems: 'flex-start', gap: 10}, dishName: {flex: 1, fontSize: 16, fontWeight: '600', color: '#1d2939'},
  price: {fontSize: 16, color: '#1d2939', fontWeight: '700'}, category: {color: blue, marginTop: 8, fontSize: 13, fontWeight: '600'},
  dishDescription: {color: '#465363', marginTop: 7, fontSize: 14, lineHeight: 20}, included: {color: '#465363', marginTop: 7, fontSize: 14},
  allergens: {color: '#7a8795', marginTop: 7, fontSize: 12}, sourceHint: {color: '#8b97a3', fontSize: 12, lineHeight: 18, marginTop: 12},
  empty: {padding: 22, backgroundColor: '#f5f7fa', borderRadius: 8}, emptyTitle: {fontSize: 16, fontWeight: '600', color: '#455365'}, emptyText: {fontSize: 13, color: '#718092', marginTop: 7},
  bottomTabs: {flexDirection: 'row', minHeight: 62, borderTopWidth: 1, borderTopColor: '#e8ebef', backgroundColor: '#fff'},
  bottomTab: {flex: 1, alignItems: 'center', justifyContent: 'center'}, bottomIcon: {fontSize: 23, color: '#a8b0bb'}, bottomLabel: {fontSize: 12, color: '#a8b0bb'}, bottomActive: {color: blue},
  contactContent: {alignItems: 'center', padding: 22, paddingBottom: 60}, contactHeading: {color: '#404e5e', fontSize: 18, fontWeight: '600', marginTop: 25, marginBottom: 15},
  actionButton: {backgroundColor: '#edf2f7', borderRadius: 8, paddingVertical: 13, paddingHorizontal: 20, minWidth: 230, alignItems: 'center', marginBottom: 10},
  actionText: {fontSize: 15, fontWeight: '700', color: '#263545'}, address: {fontSize: 14, color: '#536174', marginBottom: 12, textAlign: 'center'},
  mapWrap: {flex: 1}, pin: {height: 34, width: 34, borderRadius: 17, borderWidth: 2, borderColor: '#fff', backgroundColor: '#e53035', alignItems: 'center', justifyContent: 'center', elevation: 3}, pinText: {fontSize: 16, color: '#fff', fontWeight: '700'},
  mapNotice: {position: 'absolute', top: 10, left: 12, right: 12, backgroundColor: '#fff', padding: 9, borderRadius: 6}, mapNoticeText: {fontSize: 12, color: '#465363'},
  mapAttribution: {position: 'absolute', right: 5, bottom: 5, backgroundColor: '#ffffffdd', paddingHorizontal: 5}, mapAttributionText: {color: '#455365', fontSize: 10},
  error: {color: '#b53636', padding: 18}, errorStrip: {color: '#b53636', backgroundColor: '#fff2f2', padding: 7, textAlign: 'center', fontSize: 12},
});
