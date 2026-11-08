export type Dish = {
  name: string;
  price?: number | null;
  category?: string;
  description?: string;
  allergens?: string[];
  energy_kcal?: number | null;
  included_soup?: string | null;
  included_choices?: string[];
  price_small?: number | null;
  price_large?: number | null;
  menu_options?: {label: string; total_price: number}[];
};

export type Restaurant = {
  id: string;
  name: string;
  url?: string;
  monogram?: string;
  status?: string;
  validFrom?: string | null;
  validUntil?: string | null;
  seasonal?: Dish[];
  days: Record<string, Dish[]>;
  restaurantType?: string;
  logoUrl?: string;
  phone?: string;
  email?: string;
  hours?: string[];
  hoursSource?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  manualDays?: Record<string, boolean>;
};

export type LunchData = {
  weekStart: string;
  weekEnd: string;
  restaurants: Restaurant[];
};

const base = 'https://phoenixvie.github.io/wu-lunch/';
const supabase = 'https://vswnqdqnohbuzbwmsdvv.supabase.co';
const key = 'sb_publishable__LAhcQOUGtE-ACAN-RPKkw_UB7Nrub2';

type Override = {
  restaurant_id: string;
  is_enabled: boolean;
  sort_order: number;
  display_name?: string | null;
  restaurant_type?: string | null;
  logo_url?: string | null;
  phone?: string | null;
  email?: string | null;
  website_url?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};
type DayOverride = {restaurant_id: string; menu_date: string; dishes: Dish[]};

async function publicRows<T>(path: string): Promise<T[]> {
  const response = await fetch(supabase + '/rest/v1/' + path, {
    headers: {apikey: key},
  });
  if (!response.ok) throw new Error('Live-Daten konnten nicht geladen werden.');
  return response.json();
}

export function displayWeekStart(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Vienna', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(now);
  const part = (type: string) => parts.find(item => item.type === type)?.value || '';
  const today = new Date(`${part('year')}-${part('month')}-${part('day')}T12:00:00Z`);
  const weekday = today.getUTCDay();
  const move = weekday === 6 ? 2 : weekday === 0 ? 1 : 1 - weekday;
  today.setUTCDate(today.getUTCDate() + move);
  return today.toISOString().slice(0, 10);
}

export async function loadLunchData(weekStart = displayWeekStart()): Promise<LunchData> {
  const response = await fetch(base + 'data/menus.json?t=' + Date.now(), {cache: 'no-store'});
  if (!response.ok) throw new Error('Menüs konnten nicht geladen werden.');
  const data: LunchData = await response.json();
  if (!data.weekStart || !Array.isArray(data.restaurants)) throw new Error('Ungültige Menüdaten.');
  const [profiles, manualDays, contacts] = await Promise.all([
    publicRows<Override>('restaurant_overrides?select=*'),
    publicRows<DayOverride>('menu_day_overrides?week_start=eq.' + weekStart + '&select=restaurant_id,menu_date,dishes'),
    fetch(base + 'data/restaurant-contact.json?t=' + Date.now(), {cache: 'no-store'}).then(async response => response.ok ? ((await response.json()).restaurants || {}) as Record<string,{phone?: string; email?: string; hours?: string[]; source?: string}> : {} as Record<string,{phone?: string; email?: string; hours?: string[]; source?: string}>).catch(() => ({} as Record<string,{phone?: string; email?: string; hours?: string[]; source?: string}>)),
  ]);
  const profileById = new Map(profiles.map(row => [row.restaurant_id, row]));
  const visible: Restaurant[] = [];
  for (const source of data.restaurants) {
    const profile = profileById.get(source.id);
    if (profile?.is_enabled === false) continue;
    const contact = contacts[source.id] || {};
    const restaurant: Restaurant = {...source, days: {...source.days}, manualDays: {}, phone: contact.phone, email: contact.email, hours: contact.hours, hoursSource: contact.source};
    if (profile) {
      restaurant.name = profile.display_name || restaurant.name;
      restaurant.restaurantType = profile.restaurant_type || undefined;
      restaurant.logoUrl = profile.logo_url || undefined;
      restaurant.phone = profile.phone || restaurant.phone;
      restaurant.email = profile.email || restaurant.email;
      restaurant.url = profile.website_url || restaurant.url;
      restaurant.address = profile.address || undefined;
      restaurant.latitude = profile.latitude ?? undefined;
      restaurant.longitude = profile.longitude ?? undefined;
    }
    for (const row of manualDays) {
      if (row.restaurant_id === restaurant.id) {
        restaurant.days[row.menu_date] = Array.isArray(row.dishes) ? row.dishes : [];
        restaurant.manualDays![row.menu_date] = true;
      }
    }
    visible.push(restaurant);
  }
  visible.sort((a, b) => (profileById.get(a.id)?.sort_order ?? 9999) - (profileById.get(b.id)?.sort_order ?? 9999));
  const friday = datesOfWeek(weekStart)[4];
  return {...data, weekStart, weekEnd: friday, restaurants: visible};
}

export function datesOfWeek(weekStart: string): string[] {
  const monday = new Date(weekStart + 'T12:00:00Z');
  return Array.from({length: 5}, (_, index) => {
    const date = new Date(monday);
    date.setUTCDate(monday.getUTCDate() + index);
    return date.toISOString().slice(0, 10);
  });
}

export function initialDay(data: LunchData): string {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Vienna', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(now);
  const part = (type: string) => parts.find(item => item.type === type)?.value || '';
  const current = `${part('year')}-${part('month')}-${part('day')}`;
  const days = datesOfWeek(data.weekStart);
  return days.includes(current) ? current : days[0];
}

export function displayDate(value: string, options: Intl.DateTimeFormatOptions = {weekday: 'long', day: '2-digit', month: '2-digit'}): string {
  return new Intl.DateTimeFormat('de-AT', {timeZone: 'UTC', ...options}).format(new Date(value + 'T12:00:00Z'));
}

export function displayPrice(value?: number | null): string {
  return value == null ? 'X €' : new Intl.NumberFormat('de-AT', {minimumFractionDigits: 0, maximumFractionDigits: 2}).format(value) + ' €';
}

function mealPosition(item: Dish): number {
  const category = (item.category || '').toLocaleLowerCase('de-AT');
  const name = item.name.toLocaleLowerCase('de-AT');
  if (category.includes('suppe') || category.includes('soup') || (name.includes('suppe') && !category.includes('hauptgericht'))) return 0;
  if (category.includes('salat') || category.includes('salad')) return 2;
  if (category.includes('nachspeise') || category.includes('dessert') || category.includes('süßspeise')) return 3;
  if (category.includes('menüoption') || category.includes('menükombo') || category.includes('kombination')) return 4;
  return 1;
}

export type DisplayDish = Dish & {priceLabel?: string};

export function visibleDishes(restaurant: Restaurant, date: string): DisplayDish[] {
  let raw = restaurant.days[date] || [];
  if (!restaurant.manualDays?.[date]) {
    if (raw.length && restaurant.validFrom && restaurant.validUntil && (date < restaurant.validFrom || date > restaurant.validUntil)) raw = [];
    if (!raw.length && restaurant.status === 'seasonal' && Array.isArray(restaurant.seasonal)) raw = restaurant.seasonal;
  }
  if (restaurant.id === 'mensa') {
    return raw.map(item => ({
      ...item,
      name: item.category === 'Ausgabe 5' ? 'Pizza' : item.category || item.name,
      category: undefined,
      description: item.category === 'Ausgabe 5' ? '' : [item.name, item.description].filter(Boolean).join('\n'),
      priceLabel: item.category === 'Ausgabe 5' && item.price == null ? '' : undefined,
    }));
  }
  const result: DisplayDish[] = [];
  for (const item of [...raw].sort((a, b) => mealPosition(a) - mealPosition(b))) {
    if (restaurant.id === 'topfdeckel' && /gratis-dessert zum start|dein erstes dessert geht auf uns/i.test(item.name)) continue;
    const baseName = restaurant.id === 'losteria'
      ? item.name.toLocaleLowerCase('it-IT').replace(/(^|[\s-])([a-zà-ÿ])/g, (_, separator, letter: string) => separator + letter.toLocaleUpperCase('it-IT'))
      : item.name;
    const name = baseName;
    const priceLabel = restaurant.id === 'topfdeckel' && (item.price_small != null || item.price_large != null)
      ? [item.price_small, item.price_large].map(value => value == null ? '–' : displayPrice(value)).join(' / ')
      : undefined;
    result.push({...item, name, priceLabel, description: item.description || (item.included_choices?.length ? 'Mit ' + item.included_choices.join(' oder ') : '')});
    for (const option of item.menu_options || []) {
      if (option && typeof option.label === 'string' && Number.isFinite(option.total_price) && option.total_price > 0 && option.total_price < 150) {
        result.push({name: 'Optional: ' + option.label, price: option.total_price});
      }
    }
  }
  return result;
}
