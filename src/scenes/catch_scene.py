import pygame as pg
from src.scenes.scene import Scene
from src.core.services import scene_manager
from src.entities.player import Player
from src.utils.definition import Monster
from src.utils import Logger, GameSettings
from src.core import GameManager

class CatchMonsterScene(Scene):
    def __init__(self, player: Player, wild_monster: Monster, game_manager: GameManager = None):
        self.player = player
        self.wild_monster = wild_monster
        self.game_manager = game_manager
        self.font = pg.font.SysFont("arial", 24)
        self.caught = False
        self.finished = False

    def enter(self):
        Logger.info(f"A wild {self.wild_monster.name} appeared!")

    def exit(self):
        Logger.info(f"Exiting catch scene. Caught: {self.caught}")
        # Save game after catching a Pokémon
        if self.caught and self.game_manager:
            self.game_manager.save("saves/game0.json")
            Logger.info("Game saved after catching Pokémon!")

    def update(self, dt: float):
        keys = pg.key.get_pressed()
        if keys[pg.K_SPACE] and not self.finished:
            from random import random
            if random() < 0.7:  # 70% chance
                self.player.bag.monsters.append(self.wild_monster)
                Logger.info(f"{self.wild_monster.name} was caught!")
                self.caught = True
            else:
                Logger.info(f"{self.wild_monster.name} ran away!")
            self.finished = True

        if keys[pg.K_RETURN] and self.finished:
            scene_manager.change_scene("game")  # return to game

    def draw(self, screen: pg.Surface):
        screen.fill((0, 128, 0))  # grass background
        text = self.font.render(f"A wild {self.wild_monster.name} appeared!", True, (255, 255, 255))
        screen.blit(text, (50, 50))
        instructions = self.font.render("Press SPACE to catch, ENTER to continue", True, (255, 255, 255))
        screen.blit(instructions, (50, 100))
        if self.finished:
            status_text = "Caught!" if self.caught else "It ran away!"
            status = self.font.render(status_text, True, (255, 255, 0))
            screen.blit(status, (50, 150))
