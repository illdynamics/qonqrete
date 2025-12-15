we have this error, fix it

└[/xx/qonqrete-demo/qonqrete/worqspace/qage_20251215_015103/qodeyard]> python main.py
pygame 2.6.1 (SDL 2.28.4, Python 3.13.9)
Hello from the pygame community. https://www.pygame.org/contribute.html
Traceback (most recent call last):
  File "/xx/qonqrete-demo/qonqrete/worqspace/qage_20251215_015103/qodeyard/main.py", line 3, in <module>
    from src.game_loop import run_game
  File "/xx/qonqrete-demo/qonqrete/worqspace/qage_20251215_015103/qodeyard/src/game_loop.py", line 6, in <module>
    from src.game_logic import reset_game_state, update_game_state
  File "/xx/qonqrete-demo/qonqrete/worqspace/qage_20251215_015103/qodeyard/src/game_logic.py", line 5, in <module>
    from src.food import Food
ModuleNotFoundError: No module named 'src.food'

