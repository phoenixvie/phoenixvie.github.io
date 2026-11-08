export type Dish = {
  name: string;
  price?: number | null;
  category?: string;
  description?: string;
  allergens?: string[];
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

export async function loadLunchData(): Promise<LunchData> {
  const response = await fetch(base + 'data/menus.json?t=' + Date.now(), {cache: 'no-store'});
  if (!response.ok) throw new Error('Menüs konnten nicht geladen werden.');
  const data: LunchData = await response.json();
  if (!data.weekStart || !Array.isArray(data.restaurants)) throw new Error('Ungültige Menüdaten.');
  const [profiles, manualDays] = await Promise.all([
    publicRows<Override>('restaurant_overrides?select=*'),
    publicRows<DayOverride>('menu_day_overrides?week_start=eq.' + data.weekStart + '&select=restaurant_id,menu_date,dishes'),
  ]);
  const profileById = new Map(profiles.map(row => [row.restaurant_id, row]));
  const visible: Restaurant[] = [];
  for (const source of data.restaurants) {
    const profile = profileById.get(source.id);
    if (profile?.is_enabled === false) continue;
    const restaurant: Restaurant = {...source, days: {...source.days}, manualDays: {}};
    if (profile) {
      restaurant.name = profile.display_name || restaurant.name;
      restaurant.restaurantType = profile.restaurant_type || undefined;
      restaurant.logoUrl = profile.logo_url || undefined;
      restaurant.phone = profile.phone || undefined;
      restaurant.email = profile.email || undefined;
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
  return {...data, restaurants: visible};
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

function includedPrefix(item: Dish, restaurantId: string): string {
  const options = item.included_choices || [];
  const soup = item.included_soup;
  if (options.length) {
    const normalized = options.map(value => value.toLocaleLowerCase('de-AT'));
    if (normalized.some(value => value.includes('suppe')) && normalized.some(value => value.includes('salat'))) {
      return (soup || 'Suppe') + ' oder ' + (restaurantId === 'baschly' ? 'kleiner Salat' : 'Salat') + ' + ';
    }
    return options.join(' oder ') + ' + ';
  }
  if (restaurantId === 'glashaus') return 'Suppe oder Salat + ';
  if (restaurantId === 'baschly') return 'Tagessuppe oder kleiner Salat + ';
  return '';
}

export type DisplayDish = Dish & {priceLabel?: string};

export function visibleDishes(restaurant: Restaurant, date: string): DisplayDish[] {
  let raw = restaurant.days[date] || [];
  if (!restaurant.manualDays?.[date]) {
    if (raw.length && restaurant.validFrom && restaurant.validUntil && (date < restaurant.validFrom || date > restaurant.validUntil)) raw = [];
    if (!raw.length && restaurant.status === 'seasonal' && Array.isArray(restaurant.seasonal)) raw = restaurant.seasonal;
  }
  if (restaurant.id === 'mensa') {
    const soup = raw.find(item => item.category === 'Tagessuppe');
    return raw.filter(item => item.category !== 'Tagessuppe').map(item => ({
      ...item,
      name: (soup && !['Global & Grill', 'Pizza & Co', 'Bowls & Co', 'Pasta & Co'].includes(item.category || '') ? soup.name + ' + ' : '') + item.name,
    }));
  }
  const result: DisplayDish[] = [];
  for (const item of [...raw].sort((a, b) => mealPosition(a) - mealPosition(b))) {
    const standaloneSoup = mealPosition(item) === 0;
    const baseName = restaurant.id === 'losteria'
      ? item.name.toLocaleLowerCase('it-IT').replace(/(^|[\s-])([a-zà-ÿ])/g, (_, separator, letter: string) => separator + letter.toLocaleUpperCase('it-IT'))
      : item.name;
    const name = (standaloneSoup ? '' : includedPrefix(item, restaurant.id)) + baseName + (restaurant.id === 'topfdeckel' && item.category === 'Suppe' ? ' (klein/groß)' : '');
    const priceLabel = restaurant.id === 'topfdeckel' && (item.price_small != null || item.price_large != null)
      ? [item.price_small, item.price_large].map(value => value == null ? '–' : displayPrice(value)).join(' / ')
      : undefined;
    result.push({...item, name, priceLabel});
    for (const option of item.menu_options || []) {
      if (option && typeof option.label === 'string' && Number.isFinite(option.total_price) && option.total_price > 0 && option.total_price < 150) {
        result.push({name: 'Optional: ' + option.label, price: option.total_price});
      }
    }
  }
  return result;
}
