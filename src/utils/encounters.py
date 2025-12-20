
import random
import pygame as pg
from pathlib import Path
from src.utils.definition import Monster

ASSETS_DIR = Path("assets")

# Evolution data: maps Pokemon name to evolution details
EVOLUTION_DATA = {
    "Bulbasaur": {"evolved_form": "Ivysaur", "level": 16, "sprite_path": "menu_sprites/menusprite2.png", "stat_mult": {"hp": 1.3, "max_hp": 1.3}},
    "Ivysaur": {"evolved_form": "Venusaur", "level": 32, "sprite_path": "menu_sprites/menusprite3.png", "stat_mult": {"hp": 1.5, "max_hp": 1.5}},
    "Charmander": {"evolved_form": "Charmeleon", "level": 16, "sprite_path": "menu_sprites/menusprite8.png", "stat_mult": {"hp": 1.5, "max_hp": 1.5}},
    "Charmeleon": {"evolved_form": "Charizard", "level": 36, "sprite_path": "menu_sprites/menusprite9.png", "stat_mult": {"hp": 2.6, "max_hp": 2.6}},
    "Squirtle": {"evolved_form": "Wartortle", "level": 16, "sprite_path": "menu_sprites/menusprite13.png", "stat_mult": {"hp": 1.4, "max_hp": 1.4}},
    "Wartortle": {"evolved_form": "Blastoise", "level": 36, "sprite_path": "menu_sprites/menusprite14.png", "stat_mult": {"hp": 2.0, "max_hp": 2.0}},
    "Bug": {"evolved_form": "Beetle", "level": 20, "sprite_path": "menu_sprites/menusprite16.png", "stat_mult": {"hp": 2.4, "max_hp": 2.4}},
}

def evolve_pokemon(pokemon: dict) -> bool:
    """Evolve a Pokemon if it meets requirements. Returns True if evolved."""
    pokemon_name = pokemon.get("name", "")
    if pokemon_name not in EVOLUTION_DATA:
        return False
    
    evo_data = EVOLUTION_DATA[pokemon_name]
    if pokemon.get("level", 0) < evo_data["level"]:
        return False
    
    # Apply evolution
    stat_mult = evo_data["stat_mult"]
    old_level = pokemon.get("level", 1)
    pokemon["name"] = evo_data["evolved_form"]
    pokemon["sprite_path"] = evo_data["sprite_path"]
    pokemon["sprite"] = None  # Will be reloaded
    pokemon["hp"] = int(pokemon.get("hp", 50) * stat_mult.get("hp", 1.2))
    pokemon["max_hp"] = int(pokemon.get("max_hp", 50) * stat_mult.get("max_hp", 1.2))
    pokemon["level"] = old_level  # Preserve level after evolution
    # Update evolution data for new form
    new_name = evo_data["evolved_form"]
    if new_name in EVOLUTION_DATA:
        next_evo = EVOLUTION_DATA[new_name]
        pokemon["evolved_form"] = next_evo["evolved_form"]
        pokemon["evolution_level"] = next_evo["level"]
    else:
        pokemon["evolved_form"] = ""
        pokemon["evolution_level"] = 0
    return True

def generate_random_monster() -> dict:
    """Generate a random wild monster dict for battle."""
    wild_monsters = [
        # Venusaur line (menusprite 1, 2, 3)
        {"name": "Bulbasaur",  "hp": 45,  "max_hp": 60,  "level": 15, "sprite_path": "menu_sprites/menusprite1.png", "element": "Grass", "evolved_form": "Ivysaur", "evolution_level": 16},
        {"name": "Ivysaur",    "hp": 60,  "max_hp": 80,  "level": 16, "sprite_path": "menu_sprites/menusprite2.png", "element": "Grass", "evolved_form": "Venusaur", "evolution_level": 32},
        {"name": "Venusaur",   "hp": 90,  "max_hp": 160, "level": 30, "sprite_path": "menu_sprites/menusprite3.png", "element": "Grass", "evolved_form": "", "evolution_level": 0},
        
        # Charizard line (menusprite 7, 8, 9)
        {"name": "Charmander", "hp": 39,  "max_hp": 50,  "level": 15, "sprite_path": "menu_sprites/menusprite7.png", "element": "Fire", "evolved_form": "Charmeleon", "evolution_level": 16},
        {"name": "Charmeleon", "hp": 58,  "max_hp": 75,  "level": 16, "sprite_path": "menu_sprites/menusprite8.png", "element": "Fire", "evolved_form": "Charizard", "evolution_level": 36},
        {"name": "Charizard",  "hp": 150, "max_hp": 200, "level": 40, "sprite_path": "menu_sprites/menusprite9.png", "element": "Fire", "evolved_form": "", "evolution_level": 0},
        
        # Blastoise line (menusprite 12, 13, 14)
        {"name": "Squirtle",   "hp": 44,  "max_hp": 55,  "level": 15, "sprite_path": "menu_sprites/menusprite12.png", "element": "Water", "evolved_form": "Wartortle", "evolution_level": 16},
        {"name": "Wartortle",  "hp": 59,  "max_hp": 80,  "level": 16, "sprite_path": "menu_sprites/menusprite13.png", "element": "Water", "evolved_form": "Blastoise", "evolution_level": 36},
        {"name": "Blastoise",  "hp": 120, "max_hp": 180, "level": 40, "sprite_path": "menu_sprites/menusprite14.png", "element": "Water", "evolved_form": "", "evolution_level": 0},
        
        # Pikachu line (menusprite 15, 16)
        {"name": "Bug",      "hp": 35,  "max_hp": 50,  "level": 30, "sprite_path": "menu_sprites/menusprite15.png", "element": "Electric", "evolved_form": "Beetle", "evolution_level": 20},
        {"name": "Beetle",    "hp": 85,  "max_hp": 100, "level": 40, "sprite_path": "menu_sprites/menusprite16.png", "element": "Electric", "evolved_form": "", "evolution_level": 0},
        
        # Other available sprites (4, 5, 6, 10, 11)
        {"name": "Capybara",   "hp": 45,  "max_hp": 60,  "level": 5, "sprite_path": "menu_sprites/menusprite4.png", "element": "Ground", "evolved_form": "", "evolution_level": 0},
        {"name": "Pidgey",     "hp": 39,  "max_hp": 50,  "level": 5, "sprite_path": "menu_sprites/menusprite5.png", "element": "Flying", "evolved_form": "", "evolution_level": 0},
        {"name": "Arcanine",   "hp": 110, "max_hp": 155, "level": 12, "sprite_path": "menu_sprites/menusprite6.png", "element": "Ice", "evolved_form": "", "evolution_level": 0},
        {"name": "Rattata",    "hp": 44,  "max_hp": 55,  "level": 5, "sprite_path": "menu_sprites/menusprite10.png", "element": "Normal", "evolved_form": "", "evolution_level": 0},
        {"name": "Dragonite",  "hp": 55,  "max_hp": 95,  "level": 9, "sprite_path": "menu_sprites/menusprite11.png", "element": "Psychic", "evolved_form": "", "evolution_level": 0},
    ]
    choice = random.choice(wild_monsters)
    
    # Don't load sprite here - let battle_scene handle sprite loading
    # This allows battle_scene to use sprite_idle.png instead of menu sprites
    choice["sprite"] = None
    return choice