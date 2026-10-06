//! Auditable base-game metadata. Color order: white, blue, green, red, black.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Card {
    pub tier: u8,
    pub bonus: u8,
    pub points: u8,
    pub cost: [u8; 5],
}
pub const CARDS: [Card; 90] = [
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [1, 1, 1, 1, 0],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [1, 2, 1, 1, 0],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [2, 2, 0, 1, 0],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [0, 0, 1, 3, 1],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [0, 0, 2, 1, 0],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [2, 0, 2, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 0,
        cost: [0, 0, 3, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 4,
        points: 1,
        cost: [0, 4, 0, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [1, 0, 1, 1, 1],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [1, 0, 1, 2, 1],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [1, 0, 2, 2, 0],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [0, 1, 3, 1, 0],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [1, 0, 0, 0, 2],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [0, 0, 2, 0, 2],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 0,
        cost: [0, 0, 0, 0, 3],
    },
    Card {
        tier: 0,
        bonus: 1,
        points: 1,
        cost: [0, 0, 0, 4, 0],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [0, 1, 1, 1, 1],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [0, 1, 2, 1, 1],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [0, 2, 2, 0, 1],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [3, 1, 0, 0, 1],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [0, 0, 0, 2, 1],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [0, 2, 0, 0, 2],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 0,
        cost: [0, 3, 0, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 0,
        points: 1,
        cost: [0, 0, 4, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [1, 1, 0, 1, 1],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [1, 1, 0, 1, 2],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [0, 1, 0, 2, 2],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [1, 3, 1, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [2, 1, 0, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [0, 2, 0, 2, 0],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 0,
        cost: [0, 0, 0, 3, 0],
    },
    Card {
        tier: 0,
        bonus: 2,
        points: 1,
        cost: [0, 0, 0, 0, 4],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [1, 1, 1, 0, 1],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [2, 1, 1, 0, 1],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [2, 0, 1, 0, 2],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [1, 0, 0, 1, 3],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [0, 2, 1, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [2, 0, 0, 2, 0],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 0,
        cost: [3, 0, 0, 0, 0],
    },
    Card {
        tier: 0,
        bonus: 3,
        points: 1,
        cost: [4, 0, 0, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 4,
        points: 1,
        cost: [3, 2, 2, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 4,
        points: 1,
        cost: [3, 0, 3, 0, 2],
    },
    Card {
        tier: 1,
        bonus: 4,
        points: 2,
        cost: [0, 1, 4, 2, 0],
    },
    Card {
        tier: 1,
        bonus: 4,
        points: 2,
        cost: [0, 0, 5, 3, 0],
    },
    Card {
        tier: 1,
        bonus: 4,
        points: 2,
        cost: [5, 0, 0, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 4,
        points: 3,
        cost: [0, 0, 0, 0, 6],
    },
    Card {
        tier: 1,
        bonus: 1,
        points: 1,
        cost: [0, 2, 2, 3, 0],
    },
    Card {
        tier: 1,
        bonus: 1,
        points: 1,
        cost: [0, 2, 3, 0, 3],
    },
    Card {
        tier: 1,
        bonus: 1,
        points: 2,
        cost: [5, 3, 0, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 1,
        points: 2,
        cost: [2, 0, 0, 1, 4],
    },
    Card {
        tier: 1,
        bonus: 1,
        points: 2,
        cost: [0, 5, 0, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 1,
        points: 3,
        cost: [0, 6, 0, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 0,
        points: 1,
        cost: [0, 0, 3, 2, 2],
    },
    Card {
        tier: 1,
        bonus: 0,
        points: 1,
        cost: [2, 3, 0, 3, 0],
    },
    Card {
        tier: 1,
        bonus: 0,
        points: 2,
        cost: [0, 0, 1, 4, 2],
    },
    Card {
        tier: 1,
        bonus: 0,
        points: 2,
        cost: [0, 0, 0, 5, 3],
    },
    Card {
        tier: 1,
        bonus: 0,
        points: 2,
        cost: [0, 0, 0, 5, 0],
    },
    Card {
        tier: 1,
        bonus: 0,
        points: 3,
        cost: [6, 0, 0, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 2,
        points: 1,
        cost: [3, 0, 2, 3, 0],
    },
    Card {
        tier: 1,
        bonus: 2,
        points: 1,
        cost: [2, 3, 0, 0, 2],
    },
    Card {
        tier: 1,
        bonus: 2,
        points: 2,
        cost: [4, 2, 0, 0, 1],
    },
    Card {
        tier: 1,
        bonus: 2,
        points: 2,
        cost: [0, 5, 3, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 2,
        points: 2,
        cost: [0, 0, 5, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 2,
        points: 3,
        cost: [0, 0, 6, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 3,
        points: 1,
        cost: [2, 0, 0, 2, 3],
    },
    Card {
        tier: 1,
        bonus: 3,
        points: 1,
        cost: [0, 3, 0, 2, 3],
    },
    Card {
        tier: 1,
        bonus: 3,
        points: 2,
        cost: [1, 4, 2, 0, 0],
    },
    Card {
        tier: 1,
        bonus: 3,
        points: 2,
        cost: [3, 0, 0, 0, 5],
    },
    Card {
        tier: 1,
        bonus: 3,
        points: 2,
        cost: [0, 0, 0, 0, 5],
    },
    Card {
        tier: 1,
        bonus: 3,
        points: 3,
        cost: [0, 0, 0, 6, 0],
    },
    Card {
        tier: 2,
        bonus: 4,
        points: 3,
        cost: [3, 3, 5, 3, 0],
    },
    Card {
        tier: 2,
        bonus: 4,
        points: 4,
        cost: [0, 0, 0, 7, 0],
    },
    Card {
        tier: 2,
        bonus: 4,
        points: 4,
        cost: [0, 0, 3, 6, 3],
    },
    Card {
        tier: 2,
        bonus: 4,
        points: 5,
        cost: [0, 0, 0, 7, 3],
    },
    Card {
        tier: 2,
        bonus: 1,
        points: 3,
        cost: [3, 0, 3, 3, 5],
    },
    Card {
        tier: 2,
        bonus: 1,
        points: 4,
        cost: [7, 0, 0, 0, 0],
    },
    Card {
        tier: 2,
        bonus: 1,
        points: 4,
        cost: [6, 3, 0, 0, 3],
    },
    Card {
        tier: 2,
        bonus: 1,
        points: 5,
        cost: [7, 3, 0, 0, 0],
    },
    Card {
        tier: 2,
        bonus: 0,
        points: 3,
        cost: [0, 3, 3, 5, 3],
    },
    Card {
        tier: 2,
        bonus: 0,
        points: 4,
        cost: [0, 0, 0, 0, 7],
    },
    Card {
        tier: 2,
        bonus: 0,
        points: 4,
        cost: [3, 0, 0, 3, 6],
    },
    Card {
        tier: 2,
        bonus: 0,
        points: 5,
        cost: [3, 0, 0, 0, 7],
    },
    Card {
        tier: 2,
        bonus: 2,
        points: 3,
        cost: [5, 3, 0, 3, 3],
    },
    Card {
        tier: 2,
        bonus: 2,
        points: 4,
        cost: [0, 7, 0, 0, 0],
    },
    Card {
        tier: 2,
        bonus: 2,
        points: 4,
        cost: [3, 6, 3, 0, 0],
    },
    Card {
        tier: 2,
        bonus: 2,
        points: 5,
        cost: [0, 7, 3, 0, 0],
    },
    Card {
        tier: 2,
        bonus: 3,
        points: 3,
        cost: [3, 5, 3, 0, 3],
    },
    Card {
        tier: 2,
        bonus: 3,
        points: 4,
        cost: [0, 0, 7, 0, 0],
    },
    Card {
        tier: 2,
        bonus: 3,
        points: 4,
        cost: [0, 3, 6, 3, 0],
    },
    Card {
        tier: 2,
        bonus: 3,
        points: 5,
        cost: [0, 0, 7, 3, 0],
    },
];
pub const NOBLES: [[u8; 5]; 10] = [
    [4, 4, 0, 0, 0],
    [0, 4, 4, 0, 0],
    [0, 0, 4, 4, 0],
    [0, 0, 0, 4, 4],
    [4, 0, 0, 0, 4],
    [3, 3, 3, 0, 0],
    [0, 3, 3, 3, 0],
    [0, 0, 3, 3, 3],
    [3, 0, 0, 3, 3],
    [3, 3, 0, 0, 3],
];

const fn make_noble_threshold_masks() -> [[u16; 32]; 2] {
    let mut masks = [[0; 32]; 2];
    let mut noble = 0;
    while noble < 10 {
        let mut requirement = 0;
        let mut colors = 0u8;
        let mut color = 0;
        while color < 5 {
            let req = NOBLES[noble][color];
            if req != 0 {
                assert!(req == 3 || req == 4);
                assert!(requirement == 0 || requirement == req);
                requirement = req;
                colors |= 1 << color;
            }
            color += 1;
        }
        assert!(requirement == 3 || requirement == 4);
        let mut available = 0u8;
        while available < 32 {
            if available & colors == colors {
                masks[(requirement - 3) as usize][available as usize] |= 1 << noble;
            }
            available += 1;
        }
        noble += 1;
    }
    masks
}
const NOBLE_THRESHOLD_MASKS: [[u16; 32]; 2] = make_noble_threshold_masks();

/// Available nobles whose published requirements are met by these bonuses.
/// Base nobles require either three or four bonuses in each required color.
#[inline]
pub fn eligible_nobles(nobles: u16, bonuses: &[u8; 5]) -> u16 {
    let mut three = 0usize;
    let mut four = 0usize;
    for (color, &bonus) in bonuses.iter().enumerate() {
        three |= usize::from(bonus >= 3) << color;
        four |= usize::from(bonus >= 4) << color;
    }
    nobles & (NOBLE_THRESHOLD_MASKS[0][three] | NOBLE_THRESHOLD_MASKS[1][four])
}
