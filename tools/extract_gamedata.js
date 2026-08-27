// Converts the vendored gameData.js constants into brassbot/data/brass.json.
//
// The vendor file is a third-party transcription of the physical components. It
// cross-checks against the rulebook on every value that appears in both, with
// one exception, applied as an override below: it stores brewery output
// per-level, but the rule is per-era.
//
// Run: node tools/extract_gamedata.js

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const VENDOR = path.join(ROOT, 'tools/vendor/gameData.js');
if (!fs.existsSync(VENDOR)) {
  console.error(
    'Missing tools/vendor/gameData.js (not tracked: third-party, no licence).\n' +
    'Fetch it with:\n' +
    '  mkdir -p tools/vendor && curl -sL -o tools/vendor/gameData.js \\\n' +
    '    https://raw.githubusercontent.com/npow/brass-birmingham/HEAD/js/gameData.js\n' +
    'brassbot/data/brass.json is already generated and tracked; you only need\n' +
    'this to regenerate it.');
  process.exit(1);
}
const src = fs.readFileSync(VENDOR, 'utf8');

// The vendor file is plain top-level `const` declarations with no imports, so
// evaluating it in a fresh function scope and returning the bindings is safe.
const grab = new Function(`${src}
  return { INDUSTRY_DATA, CITIES, BREWERY_FARMS, MERCHANTS, MERCHANT_TILE_MIX,
           CONNECTIONS, CARD_DECK, COAL_MARKET_PRICES, COAL_MARKET_INITIAL,
           COAL_EMPTY_PRICE, IRON_MARKET_PRICES, IRON_MARKET_INITIAL,
           IRON_EMPTY_PRICE, INITIAL_MONEY, INITIAL_INCOME_SPACE, LOAN_AMOUNT,
           LOAN_INCOME_PENALTY, MAX_INCOME, MIN_INCOME, CANAL_LINK_COST,
           RAIL_LINK_COST, RAIL_DOUBLE_LINK_COST, HAND_SIZE };`);
const G = grab();


// Ids come out of the vendor file in camelCase; normalise every id to
// snake_case so the Python side has one convention throughout.
const snake = (s) => s.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
const snakeKeys = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [snake(k), v]));

// --- industries -------------------------------------------------------------
// Rulebook, Build step 4b: a brewery gets 1 beer barrel if built in the Canal
// Era, 2 if built in the Rail Era -- a function of era, never of tile level.
const industries = {};
for (const [type, tiles] of Object.entries(G.INDUSTRY_DATA)) {
  industries[snake(type)] = tiles.map((t) => {
    const out = {
      level: t.level,
      count: t.count,
      canal_era: t.canalEra,
      rail_era: t.railEra,
      cost: t.cost,
      coal_cost: t.costCoal,
      iron_cost: t.costIron,
      vp: t.vp,
      income: t.income,
      link_vp: t.linkVP,
      can_develop: t.canDevelop,
      beer_to_sell: t.beersToSell,
    };
    if (snake(type) === 'brewery') {
      out.beer_produced_canal = 1;
      out.beer_produced_rail = 2;
    } else {
      out.resource_produced = t.resourceCubes;
    }
    return out;
  });
}

// --- locations --------------------------------------------------------------
const towns = {};
for (const [id, c] of Object.entries(G.CITIES)) {
  towns[snake(id)] = { name: c.name, region: snake(c.region), slots: c.slots.map((sl) => sl.map(snake)) };
}
for (const [id, f] of Object.entries(G.BREWERY_FARMS)) {
  // Farm breweries are locations with a single brewery-only slot, reachable
  // only via a brewery or wild industry card (never a location card).
  towns[`farm_${id}`] = { name: f.name, region: 'farm', slots: [['brewery']], farm_brewery: true };
}

const merchants = {};
for (const [id, m] of Object.entries(G.MERCHANTS)) {
  merchants[snake(id)] = {
    name: m.name, slots: m.slots, min_players: m.minPlayers,
    bonus_type: m.bonusType, bonus_amount: m.bonusAmount,
  };
}

// Brewery farms are keyed 'northern'/'southern' in BREWERY_FARMS but appear
// under those bare names in CONNECTIONS; rewrite them to the prefixed town ids.
const farmIds = new Set(Object.keys(G.BREWERY_FARMS));
const locId = (s) => (farmIds.has(s) ? `farm_${snake(s)}` : snake(s));

// A link tile joins a SET of locations, usually two. The exception is the
// Kidderminster-Worcester line, which the rules say also connects both towns to
// the southern farm brewery -- no second tile is placed, or may be.
const EXTRA_ENDS = { 'kidderminster-worcester': ['farm_southern'] };

const connections = G.CONNECTIONS.map((c) => ({
  id: c.id,
  ends: [...c.cities.map(locId), ...(EXTRA_ENDS[c.id] || [])],
  canal: c.canal,
  rail: c.rail,
}));

// --- deck -------------------------------------------------------------------
const decks = {};
for (const [n, d] of Object.entries(G.CARD_DECK)) {
  decks[n] = {
    locations: snakeKeys(d.locations),
    industries: snakeKeys(d.industries),
    dual_cotton_manufacturer: d.dualCottonManufacturer || 0,
  };
}

const out = {
  _source: 'tools/vendor/gameData.js via tools/extract_gamedata.js',
  _overrides: ['brewery beer output is per-era (1 canal / 2 rail), not per-level'],
  industries,
  towns,
  merchants,
  merchant_tile_mix: Object.fromEntries(Object.entries(G.MERCHANT_TILE_MIX).map(([n, v]) => [n, v.map(snake)])),
  connections,
  decks,
  market: {
    coal: { prices: G.COAL_MARKET_PRICES, initial: G.COAL_MARKET_INITIAL, empty_price: G.COAL_EMPTY_PRICE },
    iron: { prices: G.IRON_MARKET_PRICES, initial: G.IRON_MARKET_INITIAL, empty_price: G.IRON_EMPTY_PRICE },
  },
  constants: {
    initial_money: G.INITIAL_MONEY,
    initial_income_space: G.INITIAL_INCOME_SPACE,
    loan_amount: G.LOAN_AMOUNT,
    loan_income_penalty_levels: G.LOAN_INCOME_PENALTY,
    max_income_level: G.MAX_INCOME,
    min_income_level: G.MIN_INCOME,
    canal_link_cost: G.CANAL_LINK_COST,
    rail_link_cost: G.RAIL_LINK_COST,
    rail_double_link_cost: G.RAIL_DOUBLE_LINK_COST,
    hand_size: G.HAND_SIZE,
  },
};

const dest = path.join(ROOT, 'brassbot/data/brass.json');
fs.writeFileSync(dest, JSON.stringify(out, null, 2) + '\n');
console.log(`wrote ${dest}`);
console.log(`  industries: ${Object.keys(industries).length} types`);
console.log(`  towns: ${Object.keys(towns).length}  merchants: ${Object.keys(merchants).length}  links: ${connections.length}`);
