import assert from 'node:assert/strict';
import {test} from 'node:test';
import {loadLunchData, visibleDishes, displayPrice, datesOfWeek, displayWeekStart} from './data.ts';

test('live profile and manual day override take effect, including an intentionally empty day', async () => {
  const original = globalThis.fetch;
  const menu = {
    weekStart: '2026-11-09', weekEnd: '2026-11-13',
    restaurants: [
      {id: 'mensa', name: 'WU Mensa', days: {'2026-11-09': [{name: 'Altes Gericht', price: 5}]}},
      {id: 'finn', name: 'Finn', days: {'2026-11-09': [{name: 'Automatisch', price: 9}]}},
      {id: 'lia', name: 'Lia', days: {'2026-11-09': [{name: 'Ausblenden', price: 10}]}},
    ],
  };
  globalThis.fetch = async url => {
    const value = String(url);
    const body = value.includes('menus.json') ? menu : value.includes('restaurant_overrides') ? [
      {restaurant_id: 'mensa', is_enabled: true, sort_order: 20, display_name: 'Neue Mensa', restaurant_type: 'International', logo_url: 'https://example.org/logo.png', latitude: 48.2, longitude: 16.4},
      {restaurant_id: 'finn', is_enabled: true, sort_order: 10},
      {restaurant_id: 'lia', is_enabled: false, sort_order: 30},
    ] : [
      {restaurant_id: 'mensa', menu_date: '2026-11-09', dishes: [{name: 'Manuell', price: 7}]},
      {restaurant_id: 'finn', menu_date: '2026-11-09', dishes: []},
    ];
    return new Response(JSON.stringify(body), {status: 200});
  };
  try {
    const loaded = await loadLunchData('2026-11-09');
    assert.deepEqual(loaded.restaurants.map(row => row.id), ['finn', 'mensa']);
    assert.equal(loaded.restaurants[1].name, 'Neue Mensa');
    assert.equal(loaded.restaurants[1].restaurantType, 'International');
    assert.equal(loaded.restaurants[1].days['2026-11-09'][0].name, 'Manuell');
    assert.deepEqual(loaded.restaurants[0].days['2026-11-09'], []);
    assert.equal(loaded.restaurants[0].manualDays['2026-11-09'], true);
  } finally {globalThis.fetch = original;}
});

test('dish display keeps soup first and does not invent prices', () => {
  const restaurant = {id: 'topfdeckel', name: 'Topf & Deckel', days: {'2026-11-09': [
    {name: 'Mousse', category: 'Dessert', price: null},
    {name: 'Hauptgericht', category: 'Fleisch', price: 12},
    {name: 'Tagessuppe', category: 'Suppe', price_small: 3, price_large: 5},
  ]}};
  const dishes = visibleDishes(restaurant, '2026-11-09');
  assert.deepEqual(dishes.map(row => row.name), ['Tagessuppe (klein/groß)', 'Hauptgericht', 'Mousse']);
  assert.equal(dishes[0].priceLabel, '3 € / 5 €');
  assert.equal(displayPrice(dishes[2].price), 'X €');
  assert.equal(datesOfWeek('2026-11-09')[4], '2026-11-13');
  assert.equal(displayWeekStart(new Date('2026-11-07T12:00:00Z')), '2026-11-09');
  assert.equal(displayWeekStart(new Date('2026-11-06T12:00:00Z')), '2026-11-02');
});

test('outdated source dates do not leak into a later week', () => {
  const restaurant = {id: 'finn', name: 'Finn', validFrom: '2026-11-02', validUntil: '2026-11-06', days: {'2026-11-09': [{name: 'Alt', price: 9}]}};
  assert.deepEqual(visibleDishes(restaurant, '2026-11-09'), []);
  restaurant.manualDays = {'2026-11-09': true};
  assert.equal(visibleDishes(restaurant, '2026-11-09')[0].name, 'Alt');
});
