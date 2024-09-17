# Pygame Roguelike

A minimal roguelike game made using
[pygame-ce](https://pyga.me) and
[python-tcod](https://python-tcod.readthedocs.io/).

This project started as an answer to a
[Reddit thread](https://www.reddit.com/r/roguelikedev/comments/1f4x1uz/trying_to_find_resources_for_learning_pygame_tcod/),
in [/r/roguelikedev](https://www.reddit.com/r/roguelikedev)
where u/DanielBurdock asked for resources for roguelike development using
pygame and tcod together.
After that thread, I
[wrote a one-file script](https://pastebin.com/4yBWGUA6)
as an example, but I started to
add more and more features and it became a huge file.
I made this repository to organize the code a little bit,
so it could be easier for people to navigate it.

## Requirements

The main requirements are pygame-ce, tcod, numpy and scipy.
If you have python installed and on the system `PATH`,
running the code below should create a python virtual environment
and install the requirements in such virtual environment.

```sh
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

If you are on Windows, you must run `venv/Scripts/activate` instead of `source venv/bin/activate`.

Once you have the requirements installed, you can run the game with:

```sh
python main.py
```

## Controls

**Keyboard**:
`WASD` and arrow keys for cardinal movement,
`QEZC` for diagonal movement.
Bumping into an enemy will attack it.
Space, Return or `.` to skip a turn.

**Mouse**:
Clicking on an enemy in melee range will attack it.
Clicking on your character will skip a turn.
Clicking on an explored floor tile will take the first step towards it.
(still gotta implement continuous actions to allow the player to take the complete path)

## Credits

**Tileset**:
[Dungeon Crawl Stone Soup 32x32 Tiles](https://opengameart.org/content/dungeon-crawl-32x32-tiles),
bt [multiple artists](tiles-dcss/README.txt), licensed under CC0

**Font**:
[IBM VGA 9x8](https://int10h.org/oldschool-pc-fonts/fontlist/font?ibm_vga_9x8),
The Ultimate Oldschool PC Font Pack, VileR
