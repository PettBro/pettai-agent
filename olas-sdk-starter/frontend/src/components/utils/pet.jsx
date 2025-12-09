
/* export enum PetPreviewState {
  DEAD = 'dead',
  HAPPY = 'happy',
  SAD = 'sad',
  VERY_SAD = 'very_sad',
  SICK = 'sick',
  SLEEP = 'sleep',

  // DIRTY
  DEAD_DIRTY = 'dead_dirty',
  HAPPY_DIRTY = 'happy_dirty',
  SAD_DIRTY = 'sad_dirty',
  VERY_SAD_DIRTY = 'very_sad_dirty',
  SICK_DIRTY = 'sick_dirty',
  SLEEP_DIRTY = 'sleep_dirty',

  // STINKY
  DEAD_STINKY = 'dead_stinky',
  HAPPY_STINKY = 'happy_stinky',
  SAD_STINKY = 'sad_stinky',
  VERY_SAD_STINKY = 'very_sad_stinky',
  SICK_STINKY = 'sick_stinky',
  SLEEP_STINKY = 'sleep_stinky',

  export enum PetPreviewBackground {
  NONE = 'none',
  ART_STUDIO = 'art_studio',
  BATHROOM = 'bathroom',
  BEDROOM = 'bedroom', // do not input _day or _night, its done automatically in the service.
  BORN = 'born',
  CANDY_SHOP = 'candy_shop',
  DAYCARE = 'daycare',
  GARAGE = 'garage',
  GRAVEYARD = 'graveyard',
  HEAVEN = 'heaven',
  HOME_HALL = 'home_hall',
  HOTEL_HALL = 'hotel_hall',
  HOTEL_IN = 'hotel_in',
  HOTEL_ROOM = 'hotel_room',
  HOTEL_POOL = 'hotel_pool',
  KITCHEN = 'kitchen',
  LIVINGROOM = 'livingroom',
  MALL = 'mall',
  MAN_CAVE = 'man_cave',
  MOON = 'moon',
  OFFICE = 'office',
  PLAYROOM = 'playroom',
  POOL_TABLE = 'pool_table',
  SHOWER = 'shower',
  LEADERBOARD_ROOM = 'leaderboard_room',
  KOTH_ROOM = 'king_of_the_hill',
}
} */

const EMOTION_THRESHOLDS = [30, 50, 85];
// Use local assets from public folder - bundled with the app
const ASSETS_BASE_URL = process.env.PUBLIC_URL || '';

function calculateBaseEmotion(
  pet,
  noPropsPassed,
  state
) {
  if (!noPropsPassed && state) {
    // Remove _dirty and _stinky suffixes to get base emotion
    return state.toLowerCase().replace('_dirty', '').replace('_stinky', '');
  }

  if (!pet) {
    return 'happy';
  }

  let emotion = 'happy';

  // Convert stats to Decimal for comparison
  const happiness = Number(pet.PetStats.happiness);
  const health = Number(pet.PetStats.health);
  const hunger = Number(pet.PetStats.hunger);
  const hygiene = Number(pet.PetStats.hygiene);
  const energy = Number(pet.PetStats.energy);

  if (
    happiness < EMOTION_THRESHOLDS[2] ||
    health < EMOTION_THRESHOLDS[2] ||
    hunger < EMOTION_THRESHOLDS[2] ||
    hygiene < EMOTION_THRESHOLDS[2] ||
    energy < EMOTION_THRESHOLDS[2]
  ) {
    emotion = 'normal';
  }

  if (happiness < EMOTION_THRESHOLDS[1]) {
    emotion = 'sad';
  }

  if (happiness < EMOTION_THRESHOLDS[0]) {
    emotion = 'very_sad';
  }

  if (health < EMOTION_THRESHOLDS[0]) {
    emotion = 'sick';
  }

  if (pet.sleeping) {
    emotion = 'sleep';
  }

  if (pet.dead) {
    emotion = 'dead';
  }

  return emotion;
}

function shouldShowStinky(
  pet,
  noPropsPassed,
  state
) {
  if (!noPropsPassed && state) {
    return state.toLowerCase().includes('_stinky');
  }

  if (!pet) {
    return false;
  }

  const hygiene = Number(pet.PetStats.hygiene);

  return hygiene < EMOTION_THRESHOLDS[0];
}

export function generatePetLayers(
  accessories,
  pet,
  options = {}
) {
  // Support both (pet, state) and (accessories, pet, { state }) signatures but ignore accessories entirely
  let thePet = pet;
  let state = options?.state;

  const looksLikeAccessories = accessories && (Array.isArray(accessories?.equipped) || Array.isArray(accessories?.shop) || Array.isArray(accessories?.owned));
  if (!looksLikeAccessories) {
    // Called as (pet, state)
    thePet = accessories;
    state = pet;
  }

  const noPropsPassed = typeof state === 'undefined';
  const layers = [];

  // Add stinky overlay first (bottom layer) if needed
  if (shouldShowStinky(thePet, noPropsPassed, state)) {
    layers.push({
      url: `${ASSETS_BASE_URL}/stinky.gif`,
      zIndex: 1,
      type: 'stinky',
      alt: 'Stinky overlay',
    });
  }

  // Base emotion layer (pet)
  const baseEmotion = calculateBaseEmotion(thePet, noPropsPassed, state);
  layers.push({
    url: `${ASSETS_BASE_URL}/emotions/${baseEmotion}.gif`,
    zIndex: 3,
    type: 'emotion',
    alt: `Pet ${baseEmotion} emotion`,
  });

  return { layers };
}

function calculateEmotion(
  pet,
  noPropsPassed,
  state
) {
  if (!noPropsPassed && state) {
    return state.toLowerCase();
  }

  if (!pet) {
    return 'happy';
  } // fallback

  let emotion = 'happy';

  // Convert stats to Decimal for comparison
  const happiness = Number(pet.PetStats.happiness);
  const health = Number(pet.PetStats.health);
  const hunger = Number(pet.PetStats.hunger);
  const hygiene = Number(pet.PetStats.hygiene);
  const energy = Number(pet.PetStats.energy);

  if (
    happiness < EMOTION_THRESHOLDS[2] ||
    health < EMOTION_THRESHOLDS[2] ||
    hunger < EMOTION_THRESHOLDS[2] ||
    hygiene < EMOTION_THRESHOLDS[2] ||
    energy < EMOTION_THRESHOLDS[2]
  ) {
    emotion = 'normal';
  }

  if (happiness < EMOTION_THRESHOLDS[1]) {
    emotion = 'sad';
  }

  if (happiness < EMOTION_THRESHOLDS[0]) {
    emotion = 'very_sad';
  }

  if (health < EMOTION_THRESHOLDS[0]) {
    emotion = 'sick';
  }

  if (pet.sleeping) {
    emotion = 'sleep';
  }

  if (hunger < EMOTION_THRESHOLDS[1]) {
    emotion += '_dirty';
  }

  if (hygiene < EMOTION_THRESHOLDS[0]) {
    emotion += '_stinky';
  }

  if (pet.dead) {
    emotion = 'dead';
  }

  return emotion;
}

export function generatePetURL(
  accessories,
  pet,
  options = {}
) {
  const {
    background = 'none',
    head,
    held,
    back,
    toy,
    state,
  } = options;

  // Helper to check if all props are undefined
  const noPropsPassed = [head, held, back, toy, state].every(
    x => typeof x === 'undefined'
  );

  // 1. Build accessoryBlueprints: start from equipped, then override with props
  const accessoryBlueprints = [...accessories.equipped];

  // Build overwriteAccessories array from props
  const overwriteAccessories = [];

  if (typeof head !== 'undefined') {
    const found = accessories.shop.find(a => a.blueprintID === head)?.blueprintID;

    if (found) {
      // Convert IStoreAccessory to IStoreUserAccessory-like object for preview
      overwriteAccessories.push({
        ...found,
        id: 'preview',
        petId: 'preview',
        equipped: false,
        rating: 0,
        obtainedAt: null,
      });
    }
  }

  if (typeof held !== 'undefined') {
    const found = accessories.shop.find(a => a.blueprintID === held);

    if (found) {
      overwriteAccessories.push({
        ...found,
        id: 'preview',
        petId: 'preview',
        equipped: false,
        rating: 0,
        obtainedAt: null,
      });
    }
  }

  if (typeof back !== 'undefined') {
    const found = accessories.shop.find(a => a.blueprintID === back);

    if (found) {
      overwriteAccessories.push({
        ...found,
        id: 'preview',
        petId: 'preview',
        equipped: true,
        rating: 0,
        obtainedAt: null,
      });
    }
  }

  if (typeof toy !== 'undefined') {
    const found = accessories.shop.find(a => a.blueprintID === toy);

    if (found) {
      overwriteAccessories.push({
        ...found,
        id: 'preview',
        petId: 'preview',
        equipped: false,
        rating: 0,
        obtainedAt: null,
      });
    }
  }

  // Overwrite accessory types
  let overridingSpecial = false;

  for (const overwriteAccessory of overwriteAccessories) {
    const index = accessoryBlueprints.findIndex(
      a => a.type === overwriteAccessory.type
    );

    if (overwriteAccessory.type === 'special') {
      overridingSpecial = true;
    }

    if (index >= 0) {
      accessoryBlueprints[index] = overwriteAccessory;
    } else {
      accessoryBlueprints.push(overwriteAccessory);
    }
  }

  // 2. Build accessoryURL
  const specialAccessory = accessoryBlueprints.find(a => a.type === 'special');
  let accessoryURL;

  if (
    !specialAccessory ||
    (overwriteAccessories.length > 0 && !overridingSpecial)
  ) {
    // Ordered: head, handheld, wings, toy
    const accessoryOrderedList = [
      accessoryBlueprints.find(a => a.type === 'head')?.imageURL || 'none',
      accessoryBlueprints.find(a => a.type === 'handheld')?.imageURL || 'none',
      accessoryBlueprints.find(a => a.type === 'wings')?.imageURL || 'none',
      accessoryBlueprints.find(a => a.type === 'toy')?.imageURL || 'none',
    ];

    // Remove trailing "none"
    while (
      accessoryOrderedList.length > 0 &&
      accessoryOrderedList[accessoryOrderedList.length - 1] === 'none'
    ) {
      accessoryOrderedList.pop();
    }

    accessoryURL = accessoryOrderedList.join('/');
  } else {
    // Special + toy
    const toyAccessory = accessoryBlueprints.find(a => a.type === 'toy');

    if (toyAccessory) {
      accessoryURL = `${specialAccessory.imageURL}/${toyAccessory.imageURL}`;
    } else {
      accessoryURL = specialAccessory.imageURL;
    }
  }

  // 3. Calculate emotion
  let emotion = 'normal';

  if (background !== 'none') {
    emotion = calculateEmotion(pet, noPropsPassed, state);
  }

  // 4. Build finalUrl
  let finalUrl = `https://storage.googleapis.com/pettai_renders/`;

  // Handle bedroom
  if (background === 'bedroom') {
    if (pet?.sleeping) {
      finalUrl += 'bedroom_night/';
    } else {
      finalUrl += 'bedroom_day/';
    }

    // Only toy accessory is used in bedroom
    const toyImg =
      accessoryBlueprints.find(a => a.type === 'toy')?.imageURL || 'none';

    if (toyImg !== 'none') {
      accessoryURL = toyImg;
    } else {
      accessoryURL = '';
    }
  } else {
    finalUrl += `${background}/`;
  }

  // If background is not the bathroom/shower/hotel_pool, add accessories
  if (
    background !== 'bathroom' &&
    background !== 'shower' &&
    background !== 'hotel_pool' &&
    background
  ) {
    finalUrl += accessoryURL;

    if (accessoryURL.length > 0) {
      finalUrl += '/';
    }
  }

  // Add emotion
  finalUrl += emotion;

  // Add file extension
  // when overriding, any of the options is defined, use .gif
  if (head || held || back || toy) {
    finalUrl += '.gif';
  } else {
    finalUrl += '.mp4?cache=2';
  }

  return finalUrl;
}


// Default config mirrors current inline logic in Pet.tsx
export const layerStyleConfig = {
  defaults: { scale: 1, left: '0px', top: '0px' },
  byType: {
    handheld: { scale: 1.1, left: '10px', top: '40px' },
    head: { scale: 1.4, left: '-2px', top: '40px' },
    stinky: { scale: 1.4, left: '5px', top: '40px' },
    back: { scale: 1.4, left: '-10px', top: '40px' },
    toy: { scale: 1.4, left: '-10px', top: '40px' },
    special: { scale: 1.6, left: '-1px', top: '40px' },
    // emotion intentionally falls back to defaults
  },
  // Optionally override specific special accessories by name as shown in alt text
  bySpecialName: {
    // Example: 'CAP_DS': { left: '-6px' },
  },
};

export function getLayerStyle(
  layer,
  config = layerStyleConfig
) {
  const base = config.defaults;
  const typeStyle = config.byType[layer.type] || {};

  let override;

  if (layer.type === 'special' && config.bySpecialName) {
    // alt for specials is formatted like: "Special accessory: NAME"
    const namePart = layer.alt.includes(':')
      ? layer.alt.split(':').slice(1).join(':').trim()
      : '';
    if (namePart && config.bySpecialName[namePart]) {
      override = config.bySpecialName[namePart];
    }
  }

  return { ...base, ...typeStyle, ...(override || {}) };
}
