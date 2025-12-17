import pygame as pg
import json
from src.utils import GameSettings
from src.utils.definition import Monster, Item


class Bag:
    _monsters_data: list[Monster]
    _items_data: list[Item]

    def __init__(self, monsters = None, items = None):
        self._monsters_data = monsters or []
        self._items_data = items or []

    @property
    def monsters(self):
        return self._monsters_data

    @property
    def items(self):
        return self._items_data

    def update(self, dt: float):
        pass

    def draw(self, screen: pg.Surface):
        pass

    def to_dict(self) -> dict[str, object]:
        # Exclude pygame Surfaces from serialization
        monsters_serializable = []
        for mon in self._monsters_data:
            mon_dict = {k: v for k, v in mon.items() if k != "sprite"}
            monsters_serializable.append(mon_dict)
        
        items_serializable = []
        for item in self._items_data:
            item_dict = {k: v for k, v in item.items() if k != "sprite"}
            items_serializable.append(item_dict)
        
        return {
            "monsters": monsters_serializable,
            "items": items_serializable
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Bag":
        monsters_data = data.get("monsters") or []
        items_data = data.get("items") or []

    # Preload monster sprites (without convert/convert_alpha which require initialized display)
        for mon in monsters_data:
            try:
                sprite_path = mon.get("sprite_path", "")
                # Load the sprite from assets folder
                full_path = f"assets/images/{sprite_path}" if not sprite_path.startswith("assets/") else sprite_path
                mon["sprite"] = pg.image.load(full_path)
                # Don't call .convert() or .convert_alpha() - display may not be initialized yet
            except Exception as e:
                print(f"Failed to load monster sprite {mon.get('sprite_path')}: {e}")
                mon["sprite"] = pg.Surface((40,40), pg.SRCALPHA)  # placeholder

    # Preload item sprites
        for item in items_data:
            try:
                sprite_path = item.get("sprite_path", "")
                # Load the sprite from assets folder
                full_path = f"assets/images/{sprite_path}" if not sprite_path.startswith("assets/") else sprite_path
                item["sprite"] = pg.image.load(full_path)
                # Don't call .convert() or .convert_alpha() - display may not be initialized yet
            except Exception as e:
                print(f"Failed to load item sprite {item.get('sprite_path')}: {e}")
                item["sprite"] = pg.Surface((32,32), pg.SRCALPHA)  # placeholder

        bag = cls(monsters_data, items_data)
        return bag
